from __future__ import annotations

import re
from pathlib import Path

from app.config import settings

READONLY_SUBDIRS = {"skills", "books"}
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

class WorkspaceError(Exception):
    """Workspace 路径校验失败。"""

class WorkspaceManager:
    def __init__(self,root:str|None=None)->None:
        self.root=Path(root or settings.workspace_root).resolve()

    def session_dir(self,session_id:str)->Path:
        if not _SESSION_ID_RE.fullmatch(session_id):
            raise WorkspaceError(f"invalid session_id: {session_id}")

        ws = self.root / session_id
        ws.mkdir(parents=True,exist_ok=True)
        (ws / "data").mkdir(parents=True,exist_ok=True)
        (ws / "outputs").mkdir(parents=True, exist_ok=True)
        return ws

    def resolve(self,session_id:str,rel_path:str)->Path:
        rel = rel_path.strip()
        if not rel:
            raise WorkspaceError("empty rel_path")
        if rel.startswith("/") or rel.startswith("\\"):
            raise WorkspaceError("absolute path is not allowed")
        if ".." in Path(rel).parts:
            raise WorkspaceError("path traversal is not allowed")

        ws = self.session_dir(session_id)
        try:
            target = (ws / rel).resolve()
        except OSError as e:
            raise WorkspaceError(str(e)) from e
        
        try:
            target.relative_to(ws)
        except ValueError as e:
            raise WorkspaceError("path escapes workspace") from e

        return target

    def is_readonly(self,session_id:str,target: Path)->bool:
        ws = self.session_dir(session_id)
        try:
            rel = target.resolve().relative_to(ws)
        except ValueError:
            return True
        parts = rel.parts
        if not parts:
            return False
        
        return parts[0] in READONLY_SUBDIRS
        

manager = WorkspaceManager()