from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.execution.docker_util import (
    compose_project_name,
    compose_ps_has_running,
    venue_container_name,
)
from app.execution.paths import COMPOSE_FILE
from app.observability.session_log import append_container_bytes, log_for_ids
from app.workspace.manager import WorkspaceError, manager

logger = logging.getLogger(__name__)

_KEY_SEP = "\x1f"


@dataclass
class _Follower:
    proc: asyncio.subprocess.Process | None = None
    task: asyncio.Task | None = None


_followers: dict[str, _Follower] = {}


def _key(user_id: str, session_id: str) -> str:
    return f"{user_id}{_KEY_SEP}{session_id}"


def _parse_key(key: str) -> tuple[str, str]:
    user_id, session_id = key.split(_KEY_SEP, 1)
    return user_id, session_id


async def _tail_loop(key: str, proc: asyncio.subprocess.Process) -> None:
    user_id, session_id = _parse_key(key)
    log_ctx = log_for_ids(user_id, session_id)
    assert proc.stdout is not None
    try:
        while True:
            chunk = await proc.stdout.read(4096)
            if not chunk:
                break
            append_container_bytes(log_ctx, chunk)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.debug("container log follower ended (%s): %s", key, e)
    finally:
        state = _followers.get(key)
        if state and state.proc is proc:
            _followers.pop(key, None)


def _compose_log_argv(compose_path: Path, project: str) -> list[str]:
    return [
        settings.sandbox_docker_bin,
        "compose",
        "-f",
        str(compose_path),
        "-p",
        project,
        "logs",
        "-f",
        "--no-color",
        "--tail=100",
    ]


def _venue_log_argv(container_name: str) -> list[str]:
    return [
        settings.sandbox_docker_bin,
        "logs",
        "-f",
        "--tail=100",
        container_name,
    ]


def _resolve_log_argv(user_id: str, session_id: str) -> list[str] | None:
    try:
        ws = manager.session_dir(user_id, session_id)
    except WorkspaceError:
        return None

    compose_path = ws / COMPOSE_FILE
    if compose_path.is_file():
        project = compose_project_name(user_id, session_id)
        if compose_ps_has_running(str(compose_path.resolve()), project):
            return _compose_log_argv(compose_path.resolve(), project)

    name = venue_container_name(user_id, session_id)
    from app.execution.docker_util import container_running

    if container_running(name):
        return _venue_log_argv(name)
    return None


async def start_container_log_follower(user_id: str, session_id: str) -> bool:
    """Follow docker compose / venue container logs into logs/sandbox.container.log."""
    if not settings.session_log_enabled:
        return False

    key = _key(user_id, session_id)
    existing = _followers.get(key)
    if existing and existing.proc and existing.proc.returncode is None:
        return True

    argv = _resolve_log_argv(user_id, session_id)
    if not argv:
        return False

    await stop_container_log_follower(user_id, session_id)

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as e:
        logger.debug("container log follower spawn failed: %s", e)
        return False

    task = asyncio.create_task(_tail_loop(key, proc))
    _followers[key] = _Follower(proc=proc, task=task)
    return True


async def stop_container_log_follower(user_id: str, session_id: str) -> None:
    key = _key(user_id, session_id)
    state = _followers.pop(key, None)
    if not state:
        return
    if state.task and not state.task.done():
        state.task.cancel()
        try:
            await state.task
        except asyncio.CancelledError:
            pass
    if state.proc and state.proc.returncode is None:
        try:
            state.proc.terminate()
            await asyncio.wait_for(state.proc.wait(), timeout=3)
        except Exception:
            try:
                state.proc.kill()
            except Exception:
                pass


def schedule_container_log_follower(user_id: str, session_id: str) -> None:
    """Fire-and-forget from sync code paths."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(start_container_log_follower(user_id, session_id))
