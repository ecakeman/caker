from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.execution.exec_runner import ExecError, run_one_shot_command
from app.execution.paths import COMPOSE_FILE
from app.execution.docker_util import compose_project_name, compose_ps_has_running
from app.observability.session_log import (
    _utc_ts,
    append_sandbox_exec,
    append_sandbox_log,
    log_for_ids,
)

_INTERACTIVE_DENY = re.compile(
    r"^\s*(vim|vi|nvim|emacs|nano|less|more|top|htop|man)\b",
    re.IGNORECASE,
)

_PENDING_TTL_SEC = 600


@dataclass
class PendingExec:
    pending_id: str
    user_id: str
    session_id: str
    command: str
    cwd: str | None
    timeout_sec: int
    created_at: float


_pending: dict[str, PendingExec] = {}


def _purge_expired() -> None:
    now = time.time()
    expired = [pid for pid, p in _pending.items() if now - p.created_at > _PENDING_TTL_SEC]
    for pid in expired:
        _pending.pop(pid, None)


def validate_command(command: str) -> None:
    cmd = command.strip()
    if not cmd:
        raise ExecError("command is empty")
    if _INTERACTIVE_DENY.match(cmd):
        raise ExecError("interactive commands are not allowed; use non-interactive flags")


def propose_exec(
    *,
    user_id: str,
    session_id: str,
    command: str,
    cwd: str | None = None,
    timeout_sec: int = 120,
) -> PendingExec:
    _purge_expired()
    validate_command(command)
    pending = PendingExec(
        pending_id=uuid.uuid4().hex,
        user_id=user_id,
        session_id=session_id,
        command=command.strip(),
        cwd=(cwd.strip() if cwd else None) or None,
        timeout_sec=max(1, min(timeout_sec, 600)),
        created_at=time.time(),
    )
    _pending[pending.pending_id] = pending
    log_ctx = log_for_ids(user_id, session_id)
    cwd_display = (cwd.strip() if cwd else None) or settings.sandbox_venue_mount
    append_sandbox_exec(
        log_ctx,
        "exec_proposed",
        pending.command,
        meta={
            "pending_id": pending.pending_id,
            "cwd": cwd_display,
            "timeout_sec": pending.timeout_sec,
        },
    )
    append_sandbox_log(
        log_ctx,
        f"{_utc_ts()} [proposed] {pending.command} (cwd={cwd_display}, pending_id={pending.pending_id})",
    )
    return pending


def get_pending_for_session(user_id: str, session_id: str) -> PendingExec | None:
    _purge_expired()
    for p in _pending.values():
        if p.user_id == user_id and p.session_id == session_id:
            return p
    return None


def pop_pending(pending_id: str, *, user_id: str, session_id: str) -> PendingExec:
    _purge_expired()
    pending = _pending.pop(pending_id, None)
    if pending is None:
        raise ExecError("pending exec not found or expired")
    if pending.user_id != user_id or pending.session_id != session_id:
        raise ExecError("pending exec session mismatch")
    return pending


def reject_pending(pending_id: str, *, user_id: str, session_id: str) -> None:
    pop_pending(pending_id, user_id=user_id, session_id=session_id)


def approve_and_run(pending_id: str, *, user_id: str, session_id: str) -> dict:
    pending = pop_pending(pending_id, user_id=user_id, session_id=session_id)
    return run_one_shot_command(
        user_id=user_id,
        session_id=session_id,
        command=pending.command,
        cwd=pending.cwd,
        timeout_sec=pending.timeout_sec,
    )


def describe_attach_target(user_id: str, session_id: str, workspace_host: Path) -> str:
    compose_path = workspace_host / COMPOSE_FILE
    if compose_path.is_file():
        project = compose_project_name(user_id, session_id)
        if compose_ps_has_running(str(compose_path.resolve()), project):
            from app.execution.venue import first_compose_service

            try:
                service = first_compose_service(compose_path)
            except Exception:
                service = "service"
            return f"compose:{service}"
    return "venue"
