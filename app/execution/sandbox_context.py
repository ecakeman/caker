from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.execution.docker_util import compose_project_name, compose_ps_has_running
from app.execution.paths import COMPOSE_FILE
from app.execution.venue import VenueError, ensure_venue_container, first_compose_service
from app.workspace.manager import manager


def build_sandbox_context(user_id: str, session_id: str) -> str:
    """Return [SANDBOX_CONTEXT] block for system prompt injection."""
    try:
        ws = manager.session_dir(user_id, session_id)
    except Exception as e:
        return f"[SANDBOX_CONTEXT]\nsandbox_mode: true\nerror: {e}"

    compose_path = ws / COMPOSE_FILE
    lines = ["[SANDBOX_CONTEXT]", "sandbox_mode: true"]

    if compose_path.is_file():
        project = compose_project_name(user_id, session_id)
        compose_up = compose_ps_has_running(str(compose_path.resolve()), project)
        try:
            service = first_compose_service(compose_path)
        except VenueError:
            service = "unknown"
        lines.append(f"compose_file: {COMPOSE_FILE}")
        lines.append(f"compose_up: {str(compose_up).lower()}")
        if compose_up:
            lines.append(f"attach: compose:{service}")
        else:
            lines.append(f"attach_if_no_compose: venue:{settings.sandbox_venue_mount}")
    else:
        lines.append("compose_file: (none)")
        lines.append("compose_up: false")
        lines.append(f"attach: venue:{settings.sandbox_venue_mount}")

    lines.append("hint: 用户在沙箱可见文件树/编辑器/终端；你不可见终端输出。")
    lines.append("hint: 长时任务用 daemon_start / daemon_attach；文件变动用 watch_start + read logs/watch_events.jsonl。")
    return "\n".join(lines)


def build_prompt_context(user_id: str, session_id: str, *, include_sandbox: bool = True) -> str:
    """Sandbox block + cross-session user profile for system prompt injection."""
    from app.user_profile.store import build_user_profile_context, ensure_profile_link

    ensure_profile_link(user_id, session_id)
    parts: list[str] = []
    if include_sandbox:
        parts.append(build_sandbox_context(user_id, session_id))
    profile = build_user_profile_context(user_id)
    if profile:
        parts.append(profile)
    return "\n\n".join(parts)


def session_workspace_host(user_id: str, session_id: str) -> Path:
    return manager.session_dir(user_id, session_id)
