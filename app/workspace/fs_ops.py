from __future__ import annotations

import shutil
from pathlib import Path

from app.workspace.manager import WorkspaceError, manager
from app.workspace.paths import assert_writable, normalize_rel_path


class FsOpsError(Exception):
    pass


def _resolve_entry(user_id: str, session_id: str, rel_path: str) -> tuple[str, Path]:
    rel = normalize_rel_path(rel_path)
    target = manager.resolve(user_id, session_id, rel)
    return rel, target


def _assert_parent_writable(user_id: str, session_id: str, rel_dir: str) -> Path:
    rel = normalize_rel_path(rel_dir) if rel_dir else ""
    if not rel:
        raise FsOpsError("destination directory required")
    assert_writable(rel)
    parent = manager.resolve(user_id, session_id, rel)
    if not parent.exists():
        raise FsOpsError(f"not found: {rel}")
    if not parent.is_dir():
        raise FsOpsError(f"not a directory: {rel}")
    return parent


def _is_readonly_rel(rel: str) -> bool:
    parts = Path(rel).parts
    return bool(parts and parts[0] in {"skills", "books"})


def _unique_dest(parent: Path, name: str) -> Path:
    candidate = parent / name
    if not candidate.exists():
        return candidate
    stem = Path(name).stem
    suffix = Path(name).suffix
    n = 1
    while True:
        alt = parent / f"{stem} (copy {n}){suffix}"
        if not alt.exists():
            return alt
        n += 1


def mkdir(user_id: str, session_id: str, rel_path: str) -> dict:
    rel = assert_writable(rel_path)
    target = manager.resolve(user_id, session_id, rel)
    if target.exists():
        raise FsOpsError(f"already exists: {rel}")
    target.mkdir(parents=True, exist_ok=False)
    return {"ok": True, "path": rel}


def copy_entry(user_id: str, session_id: str, src: str, dest_dir: str) -> dict:
    src_rel, src_path = _resolve_entry(user_id, session_id, src)
    if not src_path.exists():
        raise FsOpsError(f"not found: {src_rel}")
    parent = _assert_parent_writable(user_id, session_id, dest_dir)
    dest_path = _unique_dest(parent, src_path.name)
    if src_path.is_dir():
        shutil.copytree(src_path, dest_path)
    else:
        shutil.copy2(src_path, dest_path)
    dest_rel = dest_path.relative_to(manager.session_dir(user_id, session_id)).as_posix()
    return {"ok": True, "src": src_rel, "dest": dest_rel}


def move_entry(user_id: str, session_id: str, src: str, dest: str) -> dict:
    src_rel, src_path = _resolve_entry(user_id, session_id, src)
    if _is_readonly_rel(src_rel):
        raise FsOpsError("cannot modify readonly path")
    if not src_path.exists():
        raise FsOpsError(f"not found: {src_rel}")

    dest_rel = normalize_rel_path(dest)
    assert_writable(dest_rel)
    dest_path = manager.resolve(user_id, session_id, dest_rel)
    if dest_path.exists():
        raise FsOpsError(f"already exists: {dest_rel}")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    src_path.rename(dest_path)
    return {"ok": True, "src": src_rel, "dest": dest_rel}


def delete_entry(user_id: str, session_id: str, rel_path: str) -> dict:
    rel, target = _resolve_entry(user_id, session_id, rel_path)
    if _is_readonly_rel(rel):
        raise FsOpsError("cannot delete readonly path")
    if not target.exists():
        raise FsOpsError(f"not found: {rel}")
    if target.is_dir():
        if any(target.iterdir()):
            raise FsOpsError(f"directory not empty: {rel}")
        target.rmdir()
    else:
        target.unlink()
    return {"ok": True, "path": rel}
