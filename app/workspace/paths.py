from __future__ import annotations

from pathlib import Path

from app.workspace.manager import READONLY_SUBDIRS, WorkspaceError, manager

WRITABLE_PREFIXES = ("data/", "outputs/", "compose/")
READABLE_PREFIXES = WRITABLE_PREFIXES + ("skills/", "books/")
MAX_TEXT_BYTES = 512_000
DEFAULT_READ_LIMIT = 200
MAX_READ_LIMIT = 2000


def normalize_rel_path(rel_path: str) -> str:
    rel = rel_path.strip().replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    rel = rel.lstrip("/")
    if rel.startswith("workspace/"):
        rel = rel[len("workspace/") :]
    if not rel:
        raise WorkspaceError("empty rel_path")
    if rel.startswith("/"):
        raise WorkspaceError("absolute path is not allowed")
    if ".." in Path(rel).parts:
        raise WorkspaceError("path traversal is not allowed")
    return rel


def normalize_glob_pattern(pattern: str) -> str:
    pat = pattern.strip().replace("\\", "/")
    while pat.startswith("./"):
        pat = pat[2:]
    pat = pat.lstrip("/")
    if pat.startswith("workspace/"):
        pat = pat[len("workspace/") :]
    if not pat:
        raise WorkspaceError("empty pattern")
    if pat.startswith("/"):
        raise WorkspaceError("absolute path is not allowed")
    if ".." in Path(pat).parts:
        raise WorkspaceError("path traversal is not allowed")
    return pat


def _under_prefixes(rel: str, prefixes: tuple[str, ...]) -> bool:
    if rel in {p.rstrip("/") for p in prefixes}:
        return True
    return rel.startswith(prefixes)


def is_writable_rel(rel: str) -> bool:
    try:
        rel = normalize_rel_path(rel)
    except WorkspaceError:
        return False
    return _under_prefixes(rel, WRITABLE_PREFIXES)


def is_readable_rel(rel: str) -> bool:
    try:
        rel = normalize_rel_path(rel)
    except WorkspaceError:
        return False
    return _under_prefixes(rel, READABLE_PREFIXES)


def assert_writable(rel_path: str) -> str:
    rel = normalize_rel_path(rel_path)
    if not is_writable_rel(rel):
        raise WorkspaceError("writes only allowed under data/, outputs/, or compose/")
    parts = Path(rel).parts
    if parts and parts[0] in READONLY_SUBDIRS:
        raise WorkspaceError("cannot write under readonly subdirs")
    return rel


def assert_readable(rel_path: str) -> str:
    rel = normalize_rel_path(rel_path)
    if not is_readable_rel(rel):
        raise WorkspaceError(
            "reads only allowed under data/, outputs/, compose/, skills/, or books/"
        )
    return rel


def resolve_path(user_id: str, session_id: str, rel_path: str, *, writable: bool = False) -> Path:
    rel = assert_writable(rel_path) if writable else assert_readable(rel_path)
    return manager.resolve(user_id, session_id, rel)


def resolve_write_path(user_id: str, session_id: str, rel_path: str) -> tuple[str, Path]:
    rel = assert_writable(rel_path)
    return rel, manager.resolve(user_id, session_id, rel)


def resolve_read_path(user_id: str, session_id: str, rel_path: str) -> tuple[str, Path]:
    rel = assert_readable(rel_path)
    return rel, manager.resolve(user_id, session_id, rel)
