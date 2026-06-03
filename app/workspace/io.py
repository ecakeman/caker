from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.workspace.manager import WorkspaceError
from app.workspace.paths import (
    DEFAULT_READ_LIMIT,
    MAX_READ_LIMIT,
    MAX_TEXT_BYTES,
    normalize_rel_path,
    resolve_read_path,
    resolve_write_path,
)


@dataclass(frozen=True)
class ReadFileResult:
    rel_path: str
    text: str
    offset: int
    limit: int
    total_lines: int


@dataclass(frozen=True)
class WriteFileResult:
    rel_path: str
    bytes_written: int


@dataclass(frozen=True)
class FullTextResult:
    rel_path: str
    content: str
    size: int


def _is_previewable_file(path: Path) -> bool:
    if path.is_dir():
        return False
    try:
        if path.is_symlink():
            return path.exists() and path.is_file()
        return path.is_file()
    except OSError:
        return False


def _resolve_line_offset(offset: int, total_lines: int) -> int:
    """0-based line index; negative offset counts from end (e.g. -50 = start 50 lines from EOF)."""
    if offset >= 0:
        return min(offset, total_lines)
    return max(0, total_lines + offset)


def _format_line_chunk(lines: list[str], offset: int, limit: int) -> tuple[str, int, int]:
    total = len(lines)
    resolved = _resolve_line_offset(offset, total)
    chunk = lines[resolved : resolved + limit]
    out = [f"{i:6d}|{line}" for i, line in enumerate(chunk, start=resolved + 1)]
    body = "\n".join(out) if out else "(empty range)"
    if resolved + limit < total:
        body += (
            f"\n\n(showing lines {resolved + 1}-"
            f"{min(resolved + limit, total)} of {total}; "
            f"use offset={resolved + limit} to continue)"
        )
    elif resolved > 0:
        earlier = max(0, resolved - limit)
        body += (
            f"\n\n(showing lines {resolved + 1}-"
            f"{min(resolved + limit, total)} of {total}; "
            f"use offset={earlier} or offset=-{total - earlier} for earlier lines)"
        )
    return body, total, resolved


def read_text_file(
    user_id: str,
    session_id: str,
    rel_path: str,
    *,
    offset: int = 0,
    limit: int = DEFAULT_READ_LIMIT,
) -> ReadFileResult:
    if limit < 1 or limit > MAX_READ_LIMIT:
        raise WorkspaceError(f"limit must be between 1 and {MAX_READ_LIMIT}")

    rel, target = resolve_read_path(user_id, session_id, rel_path)

    if not target.exists():
        raise WorkspaceError(f"not found: {rel}")
    if target.is_dir():
        raise WorkspaceError(f"is a directory: {rel}")
    if not _is_previewable_file(target):
        raise WorkspaceError(f"not a file: {rel}")

    size = target.stat().st_size
    if size > MAX_TEXT_BYTES:
        raise WorkspaceError(f"file too large (max {MAX_TEXT_BYTES} bytes)")

    try:
        raw = target.read_bytes()
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise WorkspaceError("binary file cannot be read as text") from e

    lines = text.splitlines()
    body, total, resolved = _format_line_chunk(lines, offset, limit)
    return ReadFileResult(
        rel_path=rel,
        text=body,
        offset=resolved,
        limit=limit,
        total_lines=total,
    )


def read_full_text(user_id: str, session_id: str, rel_path: str) -> FullTextResult:
    rel, target = resolve_read_path(user_id, session_id, rel_path)

    if not target.exists():
        raise WorkspaceError(f"not found: {rel}")
    if target.is_dir():
        raise WorkspaceError(f"is a directory: {rel}")
    if not _is_previewable_file(target):
        raise WorkspaceError(f"cannot preview: {rel}")

    size = target.stat().st_size
    if size > MAX_TEXT_BYTES:
        raise WorkspaceError(f"file too large (max {MAX_TEXT_BYTES} bytes)")

    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise WorkspaceError("binary file cannot be previewed") from e

    return FullTextResult(rel_path=rel, content=content, size=size)


def write_text_file(
    user_id: str,
    session_id: str,
    rel_path: str,
    content: str,
    *,
    encoding: str = "utf-8",
) -> WriteFileResult:
    rel, target = resolve_write_path(user_id, session_id, rel_path)

    try:
        data = content.encode(encoding)
    except UnicodeEncodeError as e:
        raise WorkspaceError(f"encoding error: {e}") from e

    if len(data) > MAX_TEXT_BYTES:
        raise WorkspaceError(f"file too large (max {MAX_TEXT_BYTES} bytes)")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return WriteFileResult(rel_path=rel, bytes_written=len(data))


def patch_unique(
    user_id: str,
    session_id: str,
    rel_path: str,
    old_string: str,
    new_string: str,
    *,
    encoding: str = "utf-8",
) -> WriteFileResult:
    rel, target = resolve_write_path(user_id, session_id, rel_path)

    if not target.is_file():
        raise WorkspaceError(f"not a file: {rel}")

    text = target.read_text(encoding=encoding, errors="replace")
    count = text.count(old_string)
    if count == 0:
        raise WorkspaceError("old_string not found")
    if count > 1:
        raise WorkspaceError(f"old_string not unique ({count} matches)")

    return write_text_file(
        user_id,
        session_id,
        rel,
        text.replace(old_string, new_string, 1),
        encoding=encoding,
    )


def normalize_path_for_tool(rel_path: str) -> str:
    """Expose normalize for handlers that only need path cleanup."""
    return normalize_rel_path(rel_path)
