from __future__ import annotations

from langchain_core.runnables.config import RunnableConfig, var_child_runnable_config

from app.mcp.types import ToolContext


def context_from_runnable_config(
    config: RunnableConfig | dict | None = None,
    *,
    default_user: str = "local",
    default_session: str = "demo",
) -> ToolContext:
    """Resolve user/session from LangGraph/LangChain RunnableConfig."""
    cfg = config
    if cfg is None:
        cfg = var_child_runnable_config.get()
    if not cfg or not isinstance(cfg, dict):
        return ToolContext(user_id=default_user, session_id=default_session)
    configurable = cfg.get("configurable") or {}
    if not isinstance(configurable, dict):
        return ToolContext(user_id=default_user, session_id=default_session)
    user_id = str(configurable.get("user_id") or default_user).strip() or default_user
    session_id = str(configurable.get("session_id") or default_session).strip() or default_session
    return ToolContext(user_id=user_id, session_id=session_id)


def context_from_run_manager(
    run_manager=None,
    *,
    config: RunnableConfig | dict | None = None,
    default_user: str = "local",
    default_session: str = "demo",
) -> ToolContext:
    """Backward-compatible helper; prefer explicit RunnableConfig when available."""
    if config is not None:
        return context_from_runnable_config(
            config, default_user=default_user, default_session=default_session
        )
    if run_manager is not None:
        rm_config = getattr(run_manager, "config", None)
        if rm_config:
            return context_from_runnable_config(
                rm_config, default_user=default_user, default_session=default_session
            )
    return context_from_runnable_config(
        None, default_user=default_user, default_session=default_session
    )
