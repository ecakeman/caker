from __future__ import annotations

import subprocess

from app.config import settings
from app.execution.docker_util import compose_project_name, compose_ps_has_running
from app.execution.paths import COMPOSE_FILE
from app.execution.venue import VenueError, ensure_venue_container, first_compose_service
from app.observability.content_store import spill_if_large
from app.observability.session_log import (
    _utc_ts,
    append_engine,
    append_sandbox_exec,
    append_sandbox_log,
    log_for_ids,
)
from app.workspace.manager import WorkspaceError, manager

MAX_OUTPUT = 8192


class ExecError(Exception):
    pass


def _shell_command(command: str, cwd: str | None) -> str:
    workdir = cwd or settings.sandbox_venue_mount
    return f"cd {workdir} && {command}"


def build_exec_argv(
    *,
    user_id: str,
    session_id: str,
    workspace_host,
    command: str,
    cwd: str | None,
) -> list[str]:
    shell_cmd = _shell_command(command, cwd)
    compose_path = workspace_host / COMPOSE_FILE
    if compose_path.is_file():
        project = compose_project_name(user_id, session_id)
        if compose_ps_has_running(str(compose_path.resolve()), project):
            service = first_compose_service(compose_path)
            return [
                settings.sandbox_docker_bin,
                "compose",
                "-f",
                str(compose_path.resolve()),
                "-p",
                project,
                "exec",
                "-T",
                service,
                "sh",
                "-lc",
                shell_cmd,
            ]

    name = ensure_venue_container(
        user_id=user_id,
        session_id=session_id,
        workspace_host=workspace_host,
    )
    return [
        settings.sandbox_docker_bin,
        "exec",
        "-i",
        name,
        "sh",
        "-lc",
        shell_cmd,
    ]


def run_one_shot_command(
    *,
    user_id: str,
    session_id: str,
    command: str,
    cwd: str | None = None,
    timeout_sec: int = 120,
) -> dict:
    try:
        ws = manager.session_dir(user_id, session_id)
    except WorkspaceError as e:
        raise ExecError(str(e)) from e

    try:
        argv = build_exec_argv(
            user_id=user_id,
            session_id=session_id,
            workspace_host=ws,
            command=command,
            cwd=cwd,
        )
    except VenueError as e:
        raise ExecError(str(e)) from e

    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise ExecError(f"timeout after {timeout_sec}s") from e
    except OSError as e:
        raise ExecError(str(e)) from e

    stdout = (proc.stdout or "")[-MAX_OUTPUT:]
    stderr = (proc.stderr or "")[-MAX_OUTPUT:]
    result = {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "command": command,
    }
    log_ctx = log_for_ids(user_id, session_id)
    cwd_display = cwd or settings.sandbox_venue_mount
    stdout_spill = spill_if_large(log_ctx, stdout, label="stdout")
    stderr_spill = spill_if_large(log_ctx, stderr, label="stderr")
    exec_meta: dict = {
        "exit_code": proc.returncode,
        "stdout": stdout[-2000:],
        "stderr": stderr[-2000:],
        "truncated": len(proc.stdout or "") > MAX_OUTPUT or len(proc.stderr or "") > MAX_OUTPUT,
    }
    if isinstance(stdout_spill, dict) and stdout_spill.get("ref"):
        exec_meta["stdout_ref"] = stdout_spill["ref"]
    if isinstance(stderr_spill, dict) and stderr_spill.get("ref"):
        exec_meta["stderr_ref"] = stderr_spill["ref"]
    append_sandbox_exec(
        log_ctx,
        "exec_complete",
        command,
        level="ERROR" if proc.returncode != 0 else "INFO",
        meta=exec_meta,
    )
    log_lines = [
        f"{_utc_ts()} [exec] exit={proc.returncode} command={command} cwd={cwd_display}",
    ]
    if stdout:
        log_lines.append("--- stdout ---")
        log_lines.append(stdout)
    if stderr:
        log_lines.append("--- stderr ---")
        log_lines.append(stderr)
    append_sandbox_log(log_ctx, "\n".join(log_lines))

    engine_meta: dict = {
        "exit_code": proc.returncode,
        "command": command,
        "cwd": cwd_display,
    }
    if isinstance(stdout_spill, str):
        if stdout:
            engine_meta["stdout_preview"] = stdout_spill
    elif isinstance(stdout_spill, dict):
        engine_meta["stdout_preview"] = stdout_spill.get("preview", stdout[:400])
        if stdout_spill.get("ref"):
            engine_meta["stdout_ref"] = stdout_spill["ref"]
        engine_meta["stdout_len"] = stdout_spill.get("len", len(stdout))
    if isinstance(stderr_spill, str):
        if stderr:
            engine_meta["stderr_preview"] = stderr_spill
    elif isinstance(stderr_spill, dict) and stderr:
        engine_meta["stderr_preview"] = stderr_spill.get("preview", stderr[:400])
        if stderr_spill.get("ref"):
            engine_meta["stderr_ref"] = stderr_spill["ref"]
    tail = "\n".join(log_lines[-6:])
    if len(tail) > 500:
        tail = tail[-500:]
    engine_meta["sandbox_log_tail"] = tail
    append_engine(
        log_ctx,
        "sandbox_exec_done",
        command,
        level="ERROR" if proc.returncode != 0 else "INFO",
        meta=engine_meta,
    )
    return result
