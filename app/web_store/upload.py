from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.workspace.manager import manager

_UPLOAD_DIR = "data/uploads"


class UploadError(Exception):
    pass


def _safe_basename(name: str) -> str:
    if "/" in name or "\\" in name or ".." in name:
        raise UploadError("invalid file name")
    base = Path(name).name.strip()
    if not base or base in {".", ".."}:
        raise UploadError("invalid file name")
    if len(base) > 255:
        raise UploadError("file name too long")
    return base


def _unique_path(directory: Path, basename: str) -> Path:
    target = directory / basename
    if not target.exists():
        return target
    stem = Path(basename).stem
    suffix = Path(basename).suffix
    for i in range(1, 1000):
        candidate = directory / f"{stem}-{i}{suffix}"
        if not candidate.exists():
            return candidate
    raise UploadError("too many files with the same name")


def save_upload(
    user_id: str,
    session_id: str,
    filename: str,
    data: bytes,
) -> dict:
    if len(data) > settings.upload_max_bytes:
        mb = settings.upload_max_bytes // (1024 * 1024)
        raise UploadError(f"file exceeds {mb}MB limit")

    basename = _safe_basename(filename)
    ws = manager.session_dir(user_id, session_id)
    upload_dir = ws / "data" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = _unique_path(upload_dir, basename)

    try:
        resolved = target.resolve()
        resolved.relative_to(ws.resolve())
    except ValueError as e:
        raise UploadError("path escapes workspace") from e

    target.write_bytes(data)
    rel = f"{_UPLOAD_DIR}/{target.name}"
    return {
        "rel_path": rel,
        "bytes": len(data),
        "filename": target.name,
    }
