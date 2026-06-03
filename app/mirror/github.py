from __future__ import annotations

import base64
import fnmatch
import logging
import re
import threading
import time
from dataclasses import dataclass

import httpx

from app.config import settings
from app.workspace.io import format_line_window
from app.workspace.manager import WorkspaceError
from app.workspace.paths import DEFAULT_READ_LIMIT, MAX_READ_LIMIT, normalize_glob_pattern, normalize_rel_path

logger = logging.getLogger(__name__)

_BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".pyc",
    ".woff",
    ".woff2",
    ".lock",
}


class MirrorError(Exception):
    pass


@dataclass(frozen=True)
class MirrorReadResult:
    rel_path: str
    text: str
    ref: str
    repo: str
    total_lines: int
    offset: int
    limit: int


_tree_cache_lock = threading.Lock()
_tree_cache: dict[str, tuple[float, list[str]]] = {}


def _repo_slug() -> str:
    slug = settings.caker_mirror_repo.strip().strip("/")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", slug):
        raise MirrorError(f"invalid mirror repo: {slug!r}")
    return slug


def _api_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "caker-mirror/1.0",
    }
    token = settings.caker_mirror_github_token.strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _normalize_mirror_path(rel_path: str) -> str:
    try:
        rel = normalize_rel_path(rel_path)
    except WorkspaceError as e:
        raise MirrorError(str(e)) from e
    if any(part.startswith(".") and part not in {".", ".."} for part in rel.split("/")):
        # allow .env.example etc.; block only hidden dirs like .git via suffix check below
        pass
    if rel.startswith(".git/") or rel == ".git":
        raise MirrorError("path not allowed")
    suffix = "." + rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
    if suffix in _BINARY_SUFFIXES:
        raise MirrorError(f"binary or unsupported file type: {rel}")
    return rel


def _normalize_mirror_pattern(pattern: str) -> str:
    try:
        return normalize_glob_pattern(pattern)
    except WorkspaceError as e:
        raise MirrorError(str(e)) from e


def _fetch_json(client: httpx.Client, url: str) -> dict | list:
    try:
        resp = client.get(url, headers=_api_headers())
    except httpx.HTTPError as e:
        raise MirrorError(f"github request failed: {e}") from e
    if resp.status_code == 404:
        raise MirrorError("not found in mirror repo")
    if resp.status_code == 403 and "rate limit" in resp.text.lower():
        raise MirrorError("github rate limit exceeded; retry later or set CAKER_MIRROR_GITHUB_TOKEN")
    if resp.status_code >= 400:
        raise MirrorError(f"github API error {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    if not isinstance(data, (dict, list)):
        raise MirrorError("unexpected github API response")
    return data


def _list_repo_paths(*, repo: str, ref: str, client: httpx.Client) -> list[str]:
    cache_key = f"{repo}@{ref}"
    ttl = max(30, settings.caker_mirror_tree_cache_ttl_sec)
    now = time.time()
    with _tree_cache_lock:
        cached = _tree_cache.get(cache_key)
        if cached and now - cached[0] < ttl:
            return list(cached[1])

    api = settings.caker_mirror_github_api.rstrip("/")
    url = f"{api}/repos/{repo}/git/trees/{ref}?recursive=1"
    data = _fetch_json(client, url)
    if not isinstance(data, dict):
        raise MirrorError("invalid tree response")
    tree = data.get("tree")
    if not isinstance(tree, list):
        raise MirrorError("invalid tree payload")

    paths: list[str] = []
    for item in tree:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "blob":
            continue
        path = str(item.get("path") or "")
        if not path or path.startswith(".git/"):
            continue
        paths.append(path)

    with _tree_cache_lock:
        _tree_cache[cache_key] = (now, paths)
    return paths


def mirror_read(
    rel_path: str,
    *,
    offset: int = 0,
    limit: int = DEFAULT_READ_LIMIT,
) -> MirrorReadResult:
    if not settings.caker_mirror_enabled:
        raise MirrorError("caker mirror is disabled")
    if limit < 1 or limit > MAX_READ_LIMIT:
        raise MirrorError(f"limit must be between 1 and {MAX_READ_LIMIT}")

    rel = _normalize_mirror_path(rel_path)
    repo = _repo_slug()
    ref = settings.caker_mirror_ref.strip() or "main"
    api = settings.caker_mirror_github_api.rstrip("/")
    url = f"{api}/repos/{repo}/contents/{rel}?ref={ref}"

    with httpx.Client(timeout=settings.caker_mirror_timeout_sec, follow_redirects=True) as client:
        data = _fetch_json(client, url)
        if not isinstance(data, dict):
            raise MirrorError("invalid contents response")
        if data.get("type") != "file":
            raise MirrorError(f"not a file in mirror: {rel}")

        encoding = data.get("encoding")
        content_b64 = data.get("content")
        if encoding != "base64" or not isinstance(content_b64, str):
            raise MirrorError("cannot decode mirror file content")

        raw = base64.b64decode(content_b64, validate=False)
        if len(raw) > settings.caker_mirror_max_bytes:
            raise MirrorError(f"file too large (max {settings.caker_mirror_max_bytes} bytes)")

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            raise MirrorError("binary file cannot be read as text") from e

    body, total, resolved, _lim = format_line_window(text, offset, limit)
    header = (
        f"[caker_mirror] repo={repo} ref={ref} path={rel}\n"
        f"(read-only; changes must be made outside the session workspace)\n\n"
    )
    return MirrorReadResult(
        rel_path=rel,
        text=header + body,
        ref=ref,
        repo=repo,
        total_lines=total,
        offset=resolved,
        limit=limit,
    )


def mirror_glob(pattern: str, *, max_results: int = 100) -> dict:
    if not settings.caker_mirror_enabled:
        raise MirrorError("caker mirror is disabled")
    if max_results < 1 or max_results > 500:
        raise MirrorError("max_results must be between 1 and 500")

    pat = _normalize_mirror_pattern(pattern)
    repo = _repo_slug()
    ref = settings.caker_mirror_ref.strip() or "main"

    with httpx.Client(timeout=settings.caker_mirror_timeout_sec, follow_redirects=True) as client:
        paths = _list_repo_paths(repo=repo, ref=ref, client=client)

    matches: list[str] = []
    for path in sorted(paths):
        if not fnmatch.fnmatch(path, pat):
            continue
        matches.append(path)
        if len(matches) >= max_results:
            break

    return {
        "ok": True,
        "repo": repo,
        "ref": ref,
        "pattern": pat,
        "count": len(matches),
        "paths": matches,
    }


def clear_tree_cache_for_tests() -> None:
    with _tree_cache_lock:
        _tree_cache.clear()
