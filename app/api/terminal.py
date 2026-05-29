from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket

from app.execution.terminal import run_terminal_session

router = APIRouter(prefix="/api/v2/web")


@router.websocket("/sessions/{session_id}/terminal")
async def session_terminal(
    websocket: WebSocket,
    session_id: str,
    user_id: str = Query(..., min_length=1),
) -> None:
    await websocket.accept()
    await run_terminal_session(
        websocket,
        user_id=user_id.strip(),
        session_id=session_id.strip(),
    )
