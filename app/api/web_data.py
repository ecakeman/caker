from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.web_store.store import WebStoreError, store
from app.web_store.upload import UploadError, save_upload

router = APIRouter(prefix="/api/v2/web")


class UserIn(BaseModel):
    id: str


class SessionIn(BaseModel):
    user_id: str


class SessionSaveIn(BaseModel):
    id: str
    title: str = "新对话"
    userId: str
    updatedAt: int | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)


class SettingsIn(BaseModel):
    activeUserId: str | None = None
    streaming: bool | None = None
    theme: str | None = None
    activeSessionByUser: dict[str, str | None] | None = None


class LegacyImportIn(BaseModel):
    users: list[dict[str, Any]] = Field(default_factory=list)
    sessions: list[dict[str, Any]] = Field(default_factory=list)
    settings: dict[str, Any] | None = None


@router.get("/users")
async def list_users() -> dict:
    store.ensure_default_user()
    return {"users": store.list_users()}


@router.post("/users")
async def create_user(body: UserIn) -> dict:
    try:
        user = store.add_user(body.id)
    except WebStoreError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "user": user}


@router.get("/settings")
async def get_settings() -> dict:
    store.ensure_default_user()
    return store.load_settings()


@router.put("/settings")
async def put_settings(body: SettingsIn) -> dict:
    patch = body.model_dump(exclude_none=True)
    return store.save_settings(patch)


@router.get("/sessions")
async def list_sessions(user_id: str) -> dict:
    try:
        sessions = store.list_sessions(user_id)
    except WebStoreError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"sessions": sessions}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, user_id: str) -> dict:
    try:
        session = store.get_session(user_id, session_id)
    except WebStoreError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return {"session": session}


@router.post("/sessions")
async def create_session(body: SessionIn) -> dict:
    try:
        session = store.create_session(body.user_id)
    except WebStoreError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "session": session}


@router.put("/sessions/{session_id}")
async def save_session(session_id: str, body: SessionSaveIn) -> dict:
    if body.id != session_id:
        raise HTTPException(status_code=400, detail="session id mismatch")
    try:
        session = store.save_session(body.model_dump())
    except WebStoreError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "session": session}


@router.post("/import-legacy")
async def import_legacy(body: LegacyImportIn) -> dict:
    counts = store.import_legacy(body.model_dump())
    return {"ok": True, "imported": counts}


@router.post("/sessions/{session_id}/upload")
async def upload_session_files(
    session_id: str,
    user_id: str,
    files: list[UploadFile] = File(...),
) -> dict:
    if not files:
        raise HTTPException(status_code=400, detail="no files provided")

    uploaded: list[dict] = []
    errors: list[str] = []

    for f in files:
        name = f.filename or "upload.bin"
        try:
            data = await f.read()
            info = save_upload(user_id, session_id, name, data)
            uploaded.append(info)
        except UploadError as e:
            errors.append(f"{name}: {e}")
        except Exception:
            errors.append(f"{name}: upload failed")

    if not uploaded and errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    return {"ok": True, "files": uploaded, "errors": errors}
