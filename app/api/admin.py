from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.execution.cleanup import destroy_session_venue
from app.mempalace import chroma_store
from app.web_store.store import WebStoreError, store
from app.workspace.manager import WorkspaceError, manager


def _stop_session_runtime(user_id: str, session_id: str) -> None:
    """Best-effort: compose down + venue container before workspace rmtree."""
    try:
        from app.execution.compose_control import ComposeError, compose_down

        compose_down(user_id, session_id)
    except (ComposeError, Exception):
        pass
    try:
        destroy_session_venue(user_id, session_id)
    except Exception:
        pass


router = APIRouter(prefix="/api/v2")


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    request: Request,
    user_id: str = Query(..., min_length=1),
) -> dict:
    uid = user_id.strip()
    sid = session_id.strip()
    if not uid or not sid:
        raise HTTPException(status_code=400, detail="user_id and session_id required")

    checkpointer = getattr(request.app.state, "checkpointer", None)
    if checkpointer is None:
        raise HTTPException(status_code=503, detail="checkpointer not ready")

    try:
        await checkpointer.adelete_thread(sid)
    except Exception as e:
        raise HTTPException(status_code=500, detail="failed to delete checkpoint") from e

    try:
        _stop_session_runtime(uid, sid)
    except Exception:
        pass

    try:
        manager.remove_session_workspace(uid, sid)
    except WorkspaceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        store.delete_session(uid, sid)
    except WebStoreError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {"ok": True, "session_id": sid, "user_id": uid}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, request: Request) -> dict:
    uid = user_id.strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id required")

    checkpointer = getattr(request.app.state, "checkpointer", None)
    if checkpointer is None:
        raise HTTPException(status_code=503, detail="checkpointer not ready")

    try:
        session_ids = store.list_session_ids(uid)
    except WebStoreError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    for sid in session_ids:
        try:
            await checkpointer.adelete_thread(sid)
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"failed to delete checkpoint for {sid}"
            ) from e
        try:
            _stop_session_runtime(uid, sid)
        except Exception:
            pass
        try:
            manager.remove_session_workspace(uid, sid)
        except WorkspaceError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        chroma_store.delete_by_user(uid)
    except Exception as e:
        raise HTTPException(status_code=500, detail="failed to delete chroma memory") from e

    try:
        manager.remove_user_workspace(uid)
    except WorkspaceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        store.delete_all_sessions_for_user(uid)
        store.remove_user(uid)
    except WebStoreError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    store.ensure_default_user()
    return {"ok": True, "user_id": uid}


@router.delete("/users/{user_id}/memory")
async def delete_user_memory_legacy(user_id: str, request: Request) -> dict:
    """兼容旧路径，行为与 DELETE /users/{user_id} 一致。"""
    return await delete_user(user_id, request)
