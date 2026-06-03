from __future__ import annotations

import logging
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

READONLY_SUBDIRS = {"skills", "books"}
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class WorkspaceError(Exception):
    """Workspace 路径校验失败。"""


def _docker_rmtree(path: Path) -> None:
    """Remove path as root inside a throwaway container (handles root-owned bind-mount files)."""
    parent = path.parent
    name = path.name
    proc = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{parent}:/parent",
            "alpine",
            "rm",
            "-rf",
            f"/parent/{name}",
        ],
        capture_output=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode(errors="replace").strip()
        raise OSError(f"docker rm failed for {path}: {err or proc.stdout.decode(errors='replace')}")
    if path.exists():
        raise OSError(f"failed to remove {path}")


def _force_rmtree(path: Path, *, allowed_root: Path) -> None:
    """Remove a directory tree; chmod retry, then docker rm as root if needed."""
    target = path.resolve()
    root = allowed_root.resolve()
    try:
        target.relative_to(root)
    except ValueError as e:
        raise WorkspaceError("path escapes workspace root") from e

    if not target.is_dir():
        return

    def _onexc(func, entry_path, exc):
        if not isinstance(exc, PermissionError):
            raise exc
        try:
            os.chmod(entry_path, stat.S_IWUSR | stat.S_IRUSR | stat.S_IXUSR)
            func(entry_path)
        except OSError as retry_exc:
            raise retry_exc from exc

    try:
        shutil.rmtree(target, onexc=_onexc)
    except OSError as exc:
        logger.warning("rmtree %s failed (%s); trying docker rm", target, exc)
        _docker_rmtree(target)


class WorkspaceManager:
    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or settings.workspace_root).resolve()

    @staticmethod
    def _validate_id(name: str, label: str) -> None:
        if not _ID_RE.fullmatch(name):
            raise WorkspaceError(f"invalid {label}: {name}")

    def session_dir(self, user_id: str, session_id: str) -> Path:
        self._validate_id(user_id, "user_id")
        self._validate_id(session_id, "session_id")

        ws = self.root / user_id / session_id
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "data").mkdir(parents=True, exist_ok=True)
        (ws / "outputs").mkdir(parents=True, exist_ok=True)
        (ws / "compose").mkdir(parents=True, exist_ok=True)
        (ws / "logs").mkdir(parents=True, exist_ok=True)

        try:
            from app.user_profile.store import ensure_profile_link

            ensure_profile_link(user_id, session_id)
        except Exception:
            logger.debug("profile link setup skipped", exc_info=True)

        skills_link = ws / "skills"
        if not skills_link.exists():
            repo_skills = Path(__file__).resolve().parents[2] / "skills"
            if repo_skills.is_dir():
                skills_link.symlink_to(repo_skills, target_is_directory=True)

        return ws

    def resolve(self, user_id: str, session_id: str, rel_path: str) -> Path:
        rel = rel_path.strip().replace("\\", "/")
        if not rel:
            raise WorkspaceError("empty rel_path")
        if rel.startswith("/"):
            raise WorkspaceError("absolute path is not allowed")
        if ".." in Path(rel).parts:
            raise WorkspaceError("path traversal is not allowed")

        ws = self.session_dir(user_id, session_id)
        target = ws / rel
        parts = Path(rel).parts

        if parts and parts[0] in READONLY_SUBDIRS:
            return target

        try:
            resolved = target.resolve()
        except OSError as e:
            raise WorkspaceError(str(e)) from e

        try:
            resolved.relative_to(ws.resolve())
        except ValueError as e:
            raise WorkspaceError("path escapes workspace") from e

        return resolved

    def is_readonly(self, user_id: str, session_id: str, target: Path) -> bool:
        ws = self.session_dir(user_id, session_id)
        try:
            rel = target.relative_to(ws)
        except ValueError:
            return True
        parts = rel.parts
        if not parts:
            return False

        return parts[0] in READONLY_SUBDIRS

    def remove_session_workspace(self, user_id: str, session_id: str) -> None:
        self._validate_id(user_id, "user_id")
        self._validate_id(session_id, "session_id")
        target = self.root / user_id / session_id
        if target.is_dir():
            _force_rmtree(target, allowed_root=self.root)

    def remove_user_workspace(self, user_id: str) -> None:
        self._validate_id(user_id, "user_id")
        target = self.root / user_id
        if target.is_dir():
            _force_rmtree(target, allowed_root=self.root)


manager = WorkspaceManager()
