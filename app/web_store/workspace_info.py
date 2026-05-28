from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from app.workspace.manager import WorkspaceError, manager


def linux_path_to_windows(linux_path: str) -> str | None:
    """WSL Linux path → Windows Explorer path (e.g. \\\\wsl.localhost\\Ubuntu\\...)."""
    if not shutil.which("wslpath"):
        return None
    resolved = str(Path(linux_path).resolve())
    try:
        return subprocess.check_output(
            ["wslpath", "-w", resolved],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def session_path_for_file_manager(session_path: str) -> str | None:
    """Path suitable for the local OS file manager (Explorer / Finder / xdg)."""
    resolved = str(Path(session_path).resolve())
    win_unc = linux_path_to_windows(resolved)
    if win_unc:
        return win_unc
    if os.name == "nt":
        return resolved
    return resolved


def session_path_for_clipboard(session_path: str) -> str:
    """Best path to copy for the user (UNC on WSL, native path otherwise)."""
    resolved = str(Path(session_path).resolve())
    return linux_path_to_windows(resolved) or resolved


def get_session_workspace_info(user_id: str, session_id: str) -> dict:
    ws = manager.session_dir(user_id, session_id)
    files: list[dict] = []
    for path in sorted(ws.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            rel = path.relative_to(ws)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] == "skills":
            continue
        files.append(
            {
                "rel_path": rel.as_posix(),
                "bytes": path.stat().st_size,
                "filename": path.name,
            }
        )
    root = manager.root.resolve()
    session_path = ws.resolve()
    try:
        session_rel = session_path.relative_to(root).as_posix()
    except ValueError:
        session_rel = session_path.name
    session_path_str = str(session_path)
    return {
        "workspace_root": str(root),
        "session_path": session_path_str,
        "session_path_windows": session_path_for_clipboard(session_path_str),
        "session_rel": session_rel,
        "user_id": user_id,
        "session_id": session_id,
        "files": files,
    }


def verify_rel_paths_exist(user_id: str, session_id: str, rel_paths: list[str]) -> dict:
    missing: list[str] = []
    found: list[str] = []
    for rel in rel_paths:
        rel = rel.strip().replace("\\", "/")
        if not rel:
            continue
        try:
            target = manager.resolve(user_id, session_id, rel)
        except WorkspaceError:
            missing.append(rel)
            continue
        if target.is_file():
            found.append(rel)
        else:
            missing.append(rel)
    return {"ok": not missing, "found": found, "missing": missing}
