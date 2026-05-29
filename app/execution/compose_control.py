from __future__ import annotations

from pathlib import Path

from app.execution.docker_util import (
    DockerError,
    compose_project_name,
    compose_ps_has_running,
    docker_available,
)
from app.execution.paths import COMPOSE_FILE
from app.workspace.manager import WorkspaceError, manager

MAX_OUTPUT = 8192
UP_TIMEOUT = 600.0
DOWN_TIMEOUT = 120.0

_COMPOSE_NOISE = (
    "level=warning",
    "pulling fs layer",
    "downloading",
    "download complete",
    "pull complete",
    "already exists",
    "the attribute 'version' is obsolete",
)


def _compose_error_detail(stderr: str, stdout: str) -> str:
    """Extract actionable lines; drop compose warnings and pull progress noise."""
    lines: list[str] = []
    for raw in f"{stderr}\n{stdout}".splitlines():
        line = raw.strip()
        if not line:
            continue
        lower = line.lower()
        if line.startswith("time=") and "level=warning" in lower:
            continue
        if any(noise in lower for noise in _COMPOSE_NOISE):
            continue
        lines.append(line)
    if lines:
        return "\n".join(lines[-10:])
    tail = (stderr or stdout or "").strip()
    return tail[-800:] if tail else "docker compose failed"


class ComposeError(Exception):
    pass


def _compose_paths(user_id: str, session_id: str) -> tuple[Path, str, str]:
    try:
        ws = manager.session_dir(user_id, session_id)
    except WorkspaceError as e:
        raise ComposeError(str(e)) from e

    compose_path = ws / COMPOSE_FILE
    if not compose_path.is_file():
        raise ComposeError(f"compose file not found: {COMPOSE_FILE}")

    project = compose_project_name(user_id, session_id)
    return compose_path.resolve(), project, COMPOSE_FILE


def compose_status(user_id: str, session_id: str) -> dict:
    if not docker_available():
        raise ComposeError("Docker is not available on this host")

    compose_path, project, rel = _compose_paths(user_id, session_id)
    running = compose_ps_has_running(str(compose_path), project)
    return {
        "running": running,
        "compose_file": rel,
        "project": project,
        "compose_path": str(compose_path),
    }


def _run_compose(user_id: str, session_id: str, subcommand: str, *, timeout: float) -> dict:
    from app.execution.docker_util import _docker

    if not docker_available():
        raise ComposeError("Docker is not available on this host")

    compose_path, project, rel = _compose_paths(user_id, session_id)
    args = [
        "compose",
        "-f",
        str(compose_path),
        "-p",
        project,
        *subcommand.split(),
    ]
    try:
        proc = _docker(args, timeout=timeout)
    except DockerError as e:
        raise ComposeError(str(e)) from e

    stdout = (proc.stdout or "")[-MAX_OUTPUT:]
    stderr = (proc.stderr or "")[-MAX_OUTPUT:]
    ok = proc.returncode == 0
    if not ok:
        detail = _compose_error_detail(stderr, stdout)
        raise ComposeError(detail)

    running = compose_ps_has_running(str(compose_path), project)
    return {
        "ok": True,
        "running": running,
        "compose_file": rel,
        "project": project,
        "stdout": stdout,
        "stderr": stderr,
    }


def compose_up(user_id: str, session_id: str) -> dict:
    return _run_compose(user_id, session_id, "up -d", timeout=UP_TIMEOUT)


def compose_down(user_id: str, session_id: str) -> dict:
    return _run_compose(user_id, session_id, "down", timeout=DOWN_TIMEOUT)
