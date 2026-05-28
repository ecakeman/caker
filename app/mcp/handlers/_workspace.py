from __future__ import annotations

from pathlib import Path

from app.mcp.types import ToolContext
from app.workspace.manager import READONLY_SUBDIRS, WorkspaceError, manager

READONLY_WRITABLE_PREFIXES = ("data/", "outputs/")


def is_writable_rel(rel: str) -> bool:
    rel = rel.strip().replace("\\", "/").lstrip("/")
    if not rel or ".." in Path(rel).parts:
        return False
    return rel.startswith(READONLY_WRITABLE_PREFIXES)


def resolve_read(ctx: ToolContext, rel_path: str) -> Path:
    return manager.resolve(ctx.user_id, ctx.session_id, rel_path)


def resolve_write(ctx: ToolContext, rel_path: str) -> Path:
    rel = rel_path.strip().replace("\\", "/")
    if not is_writable_rel(rel):
        raise WorkspaceError("writes only allowed under data/ or outputs/")
    target = manager.resolve(ctx.user_id, ctx.session_id, rel)
    parts = Path(rel).parts
    if parts and parts[0] in READONLY_SUBDIRS:
        raise WorkspaceError("cannot write under readonly subdirs")
    return target
