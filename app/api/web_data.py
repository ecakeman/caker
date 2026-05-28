from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.web_store.store import WebStoreError, store
from app.web_store.upload import UploadError, save_upload
from app.web_store.workspace_info import (
    get_session_workspace_info,
    session_path_for_clipboard,
    session_path_for_file_manager,
    verify_rel_paths_exist,
)

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


def _reveal_folder_in_os(path: str) -> dict[str, str]:
    """Open folder on the host where uvicorn runs (Explorer / Finder / xdg-open)."""
    resolved = str(Path(path).resolve())
    clipboard_path = session_path_for_clipboard(path)

    explorer = shutil.which("explorer.exe")
    if explorer:
        target = session_path_for_file_manager(path)
        if target:
            subprocess.Popen(
                [explorer, target],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {"opened_with": "explorer", "windows_path": clipboard_path}

    if os.name == "darwin":
        opener = shutil.which("open")
        if opener:
            subprocess.Popen([opener, resolved], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"opened_with": "open", "windows_path": clipboard_path}

    opener = shutil.which("xdg-open")
    if opener:
        subprocess.Popen([opener, resolved], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"opened_with": "xdg-open", "windows_path": clipboard_path}

    raise RuntimeError("no file manager available on this host")


@router.get("/workspace")
async def get_workspace(user_id: str, session_id: str) -> dict:
    try:
        info = get_session_workspace_info(user_id.strip(), session_id.strip())
    except WorkspaceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    uploads = [f for f in info["files"] if f["rel_path"].startswith("data/uploads/")]
    return {
        "ok": True,
        **info,
        "upload_count": len(uploads),
        "hint": "Agent 的 read/write/glob 仅作用于该会话目录；附件请放在 data/uploads/",
    }


@router.post("/workspace/reveal")
async def reveal_workspace(user_id: str, session_id: str) -> dict:
    try:
        info = get_session_workspace_info(user_id.strip(), session_id.strip())
        reveal = _reveal_folder_in_os(info["session_path"])
    except WorkspaceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e
    return {
        "ok": True,
        "session_path": info["session_path"],
        "session_path_windows": info.get("session_path_windows")
        or reveal.get("windows_path")
        or "",
        **reveal,
    }


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

    verify = verify_rel_paths_exist(user_id, session_id, [f["rel_path"] for f in uploaded])
    return {"ok": True, "files": uploaded, "errors": errors, "verify": verify}
