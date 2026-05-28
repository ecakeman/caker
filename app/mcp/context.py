from __future__ import annotations

from app.mcp.types import ToolContext


def context_from_run_manager(run_manager, *, default_user: str = "local", default_session: str = "demo") -> ToolContext:
    if run_manager is None:
        return ToolContext(user_id=default_user, session_id=default_session)
    cfg = getattr(run_manager, "config", None) or {}
    if not isinstance(cfg, dict):
        return ToolContext(user_id=default_user, session_id=default_session)
    configurable = cfg.get("configurable") or {}
    if not isinstance(configurable, dict):
        return ToolContext(user_id=default_user, session_id=default_session)
    user_id = str(configurable.get("user_id") or default_user).strip() or default_user
    session_id = str(configurable.get("session_id") or default_session).strip() or default_session
    return ToolContext(user_id=user_id, session_id=session_id)
