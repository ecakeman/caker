from __future__ import annotations

import re
import shutil
from pathlib import Path

from app.config import settings

READONLY_SUBDIRS = {"skills", "books"}
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class WorkspaceError(Exception):
    """Workspace 路径校验失败。"""


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
            shutil.rmtree(target)

    def remove_user_workspace(self, user_id: str) -> None:
        self._validate_id(user_id, "user_id")
        target = self.root / user_id
        if target.is_dir():
            shutil.rmtree(target)


manager = WorkspaceManager()
