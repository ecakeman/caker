from __future__ import annotations

import subprocess

from app.config import settings
from app.execution.docker_util import compose_project_name, compose_ps_has_running
from app.execution.paths import COMPOSE_FILE
from app.execution.venue import VenueError, ensure_venue_container, first_compose_service
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
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "command": command,
    }
