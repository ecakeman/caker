"""Backward-compatible session/user id helpers for legacy tool modules."""

from __future__ import annotations

from app.mcp.context import context_from_run_manager


def ids_from_run_manager(run_manager, *, default_user: str = "local", default_session: str = "demo") -> tuple[str, str]:
    ctx = context_from_run_manager(run_manager, default_user=default_user, default_session=default_session)
    return ctx.user_id, ctx.session_id
