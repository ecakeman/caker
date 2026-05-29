from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import pty
import struct
import termios

from fastapi import WebSocket, WebSocketDisconnect

from app.config import settings
from app.execution.venue import VenueError, resolve_terminal_exec
from app.workspace.manager import WorkspaceError, manager

logger = logging.getLogger(__name__)

WELCOME_BANNER = (
    "\r\n"
    "=== Caker 执行环境工作台 ===\r\n"
    "· 请在 workspace 自备 compose/docker-compose.yml\r\n"
    "· 使用左下角「启动环境」/「停止环境」在宿主机启停 compose（勿在终端内运行 docker）\r\n"
    "· 环境启动后，终端将 attach 到 compose 服务（优先 dev）\r\n"
    "· 需要模板时可问右侧对话\r\n"
    "===========================\r\n"
)


def _set_pty_size(fd: int, *, rows: int = 24, cols: int = 80) -> None:
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


async def _pty_to_websocket(master_fd: int, websocket: WebSocket) -> None:
    loop = asyncio.get_running_loop()
    while True:
        try:
            data = await loop.run_in_executor(None, os.read, master_fd, 4096)
        except OSError:
            break
        if not data:
            break
        await websocket.send_bytes(data)


async def _websocket_to_pty(websocket: WebSocket, master_fd: int) -> None:
    while True:
        msg = await websocket.receive()
        if msg["type"] == "websocket.disconnect":
            break
        data = msg.get("bytes")
        if data:
            os.write(master_fd, data)
            continue
        text = msg.get("text")
        if text:
            os.write(master_fd, text.encode("utf-8", errors="replace"))


async def run_terminal_session(
    websocket: WebSocket,
    *,
    user_id: str,
    session_id: str,
) -> None:
    try:
        ws_dir = manager.session_dir(user_id, session_id)
    except WorkspaceError as e:
        await websocket.close(code=4000, reason=str(e))
        return

    try:
        exec_argv = resolve_terminal_exec(
            user_id=user_id,
            session_id=session_id,
            workspace_host=ws_dir,
        )
    except VenueError as e:
        await websocket.close(code=4001, reason=str(e))
        return

    master_fd: int | None = None
    proc: asyncio.subprocess.Process | None = None

    try:
        master_fd, slave_fd = pty.openpty()
        _set_pty_size(master_fd)

        cmd = [settings.sandbox_docker_bin, *exec_argv]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env={**os.environ, "TERM": "xterm-256color"},
        )
        os.close(slave_fd)

        await websocket.send_text(WELCOME_BANNER)

        pty_task = asyncio.create_task(_pty_to_websocket(master_fd, websocket))
        ws_task = asyncio.create_task(_websocket_to_pty(websocket, master_fd))

        done, pending = await asyncio.wait(
            [pty_task, ws_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        for task in done:
            if task.exception() and not isinstance(task.exception(), WebSocketDisconnect):
                logger.debug("terminal task ended: %s", task.exception())
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("terminal session error")
        try:
            await websocket.send_text(f"\r\n[终端错误] {e}\r\n")
        except Exception:
            pass
    finally:
        if master_fd is not None:
            try:
                os.close(master_fd)
            except OSError:
                pass
        if proc is not None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
