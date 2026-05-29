from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.execution.paths import COMPOSE_FILE
from app.runtime.llm import clear_llm_cache
from app.web.llm_settings import fetch_openai_models, get_user_llm_profile
from app.web_store.store import WebStoreError, store
from app.web_store.upload import UploadError, save_upload
from app.workspace.io import read_full_text, write_text_file
from app.workspace.manager import WorkspaceError, manager
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


class LlmConnectionIn(BaseModel):
    id: str = "default"
    name: str = ""
    baseUrl: str = ""
    apiKey: str = ""


class LlmProfileIn(BaseModel):
    connections: list[LlmConnectionIn] | None = None
    activeConnectionId: str | None = None
    activeModelId: str | None = None


class SettingsIn(BaseModel):
    activeUserId: str | None = None
    streaming: bool | None = None
    theme: str | None = None
    activeSessionByUser: dict[str, str | None] | None = None
    llmByUser: dict[str, LlmProfileIn] | None = None


class LlmModelsIn(BaseModel):
    baseUrl: str
    apiKey: str = ""


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
    if "llmByUser" in patch and isinstance(patch["llmByUser"], dict):
        serialized: dict[str, Any] = {}
        for uid, prof in patch["llmByUser"].items():
            if hasattr(prof, "model_dump"):
                serialized[uid] = prof.model_dump(exclude_none=True)
            else:
                serialized[uid] = prof
        patch["llmByUser"] = serialized
    saved = store.save_settings(patch)
    clear_llm_cache()
    return saved


@router.get("/llm/profile")
async def get_llm_profile(user_id: str) -> dict:
    uid = user_id.strip()
    profile = get_user_llm_profile(uid)
    safe_connections = []
    for c in profile.get("connections") or []:
        if not isinstance(c, dict):
            continue
        safe_connections.append(
            {
                "id": c.get("id", "default"),
                "name": c.get("name", ""),
                "baseUrl": c.get("baseUrl", ""),
                "hasApiKey": bool(str(c.get("apiKey") or "").strip()),
            }
        )
    return {
        "connections": safe_connections,
        "activeConnectionId": profile.get("activeConnectionId"),
        "activeModelId": profile.get("activeModelId"),
    }


@router.post("/llm/models")
async def list_llm_models(body: LlmModelsIn) -> dict:
    try:
        models = await fetch_openai_models(base_url=body.baseUrl, api_key=body.apiKey)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"models": models}


@router.put("/llm/profile")
async def put_llm_profile(user_id: str, body: LlmProfileIn) -> dict:
    uid = user_id.strip()
    cur = store.load_settings()
    by_user = cur.get("llmByUser")
    if not isinstance(by_user, dict):
        by_user = {}
    incoming = body.model_dump(exclude_none=True)
    prev = by_user.get(uid)
    if isinstance(prev, dict) and incoming.get("connections"):
        prev_conns = {
            str(c.get("id")): c
            for c in (prev.get("connections") or [])
            if isinstance(c, dict)
        }
        merged: list[dict[str, Any]] = []
        for c in incoming["connections"]:
            cid = str(c.get("id", "default"))
            old = prev_conns.get(cid, {})
            api_key = c.get("apiKey")
            if not str(api_key or "").strip() and old.get("apiKey"):
                c = {**c, "apiKey": old["apiKey"]}
            merged.append(c)
        incoming["connections"] = merged
    by_user[uid] = incoming
    saved = store.save_settings({**cur, "llmByUser": by_user})
    clear_llm_cache()
    return {"ok": True, "profile": get_user_llm_profile(uid)}


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


def _is_previewable_file(path: Path) -> bool:
    """仅列出磁盘上真实存在、可读取的普通文件。"""
    if path.is_dir():
        return False
    try:
        if path.is_symlink():
            return path.exists() and path.is_file()
        return path.is_file()
    except OSError:
        return False


def _list_workspace_tree(root: Path, *, rel_prefix: str) -> list[dict[str, str]]:
    """递归列出工作区子目录下的文件夹与可预览文件。"""
    out: list[dict[str, str]] = []
    if not root.is_dir():
        return out
    try:
        children = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        return out

    for child in children:
        rel = f"{rel_prefix}/{child.name}" if rel_prefix else child.name
        try:
            if child.is_dir() and not child.is_symlink():
                out.append({"path": rel, "type": "dir"})
                out.extend(_list_workspace_tree(child, rel_prefix=rel))
            elif _is_previewable_file(child):
                out.append({"path": rel, "type": "file"})
        except OSError:
            continue
    return out


@router.get("/sessions/{session_id}/workspace/tree")
async def workspace_tree(session_id: str, user_id: str) -> dict:
    uid = user_id.strip()
    sid = session_id.strip()
    try:
        ws = manager.session_dir(uid, sid)
    except WorkspaceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    entries: list[dict[str, str]] = []
    for sub in ("data", "outputs", "compose"):
        sub_path = ws / sub
        if sub_path.is_dir():
            entries.append({"path": sub, "type": "dir"})
            entries.extend(_list_workspace_tree(sub_path, rel_prefix=sub))

    compose_exists = (ws / COMPOSE_FILE).is_file()
    return {
        "ok": True,
        "entries": entries,
        "composeFile": COMPOSE_FILE if compose_exists else None,
    }


@router.get("/sessions/{session_id}/workspace/file")
async def workspace_file(session_id: str, user_id: str, path: str) -> dict:
    uid = user_id.strip()
    sid = session_id.strip()
    if not path.strip():
        raise HTTPException(status_code=400, detail="path required")
    try:
        result = read_full_text(uid, sid, path)
    except WorkspaceError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from e
        if "directory" in msg or "cannot preview" in msg or "not a file" in msg:
            raise HTTPException(status_code=400, detail=msg) from e
        if "binary" in msg:
            raise HTTPException(status_code=415, detail=msg) from e
        if "too large" in msg:
            raise HTTPException(status_code=413, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e

    return {"ok": True, "path": result.rel_path, "content": result.content, "size": result.size}


class WorkspaceFilePutIn(BaseModel):
    content: str


class ExecApproveIn(BaseModel):
    pending_id: str


@router.get("/sessions/{session_id}/exec/pending")
async def exec_pending(session_id: str, user_id: str) -> dict:
    from app.execution.exec_pending import get_pending_for_session

    uid = user_id.strip()
    sid = session_id.strip()
    pending = get_pending_for_session(uid, sid)
    if pending is None:
        return {"ok": True, "pending": None}
    return {
        "ok": True,
        "pending": {
            "pending_id": pending.pending_id,
            "command": pending.command,
            "cwd": pending.cwd or "/workspace",
            "timeout_sec": pending.timeout_sec,
        },
    }


@router.post("/sessions/{session_id}/exec/approve")
async def exec_approve(session_id: str, user_id: str, body: ExecApproveIn) -> dict:
    from app.execution.exec_pending import ExecError, approve_and_run

    uid = user_id.strip()
    sid = session_id.strip()
    try:
        result = approve_and_run(body.pending_id, user_id=uid, session_id=sid)
    except ExecError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "result": result}


@router.post("/sessions/{session_id}/exec/reject")
async def exec_reject(session_id: str, user_id: str, body: ExecApproveIn) -> dict:
    from app.execution.exec_pending import ExecError, reject_pending

    uid = user_id.strip()
    sid = session_id.strip()
    try:
        reject_pending(body.pending_id, user_id=uid, session_id=sid)
    except ExecError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True}


@router.put("/sessions/{session_id}/workspace/file")
async def put_workspace_file(
    session_id: str,
    user_id: str,
    path: str,
    body: WorkspaceFilePutIn,
) -> dict:
    uid = user_id.strip()
    sid = session_id.strip()
    if not path.strip():
        raise HTTPException(status_code=400, detail="path required")

    try:
        result = write_text_file(uid, sid, path, body.content)
    except WorkspaceError as e:
        msg = str(e)
        if "readonly" in msg or "writes only" in msg:
            raise HTTPException(status_code=403, detail=msg) from e
        if "too large" in msg:
            raise HTTPException(status_code=413, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e

    return {"ok": True, "path": result.rel_path, "size": result.bytes_written}


@router.get("/sessions/{session_id}/compose/status")
async def compose_status_route(session_id: str, user_id: str) -> dict:
    from app.execution.compose_control import ComposeError, compose_status

    uid = user_id.strip()
    sid = session_id.strip()
    try:
        status = compose_status(uid, sid)
    except ComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, **status}


@router.post("/sessions/{session_id}/compose/up")
async def compose_up_route(session_id: str, user_id: str) -> dict:
    from app.execution.compose_control import ComposeError, compose_up

    uid = user_id.strip()
    sid = session_id.strip()
    try:
        result = compose_up(uid, sid)
    except ComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result


@router.post("/sessions/{session_id}/compose/down")
async def compose_down_route(session_id: str, user_id: str) -> dict:
    from app.execution.compose_control import ComposeError, compose_down

    uid = user_id.strip()
    sid = session_id.strip()
    try:
        result = compose_down(uid, sid)
    except ComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result


class WorkspaceMkdirIn(BaseModel):
    path: str


class WorkspaceCopyIn(BaseModel):
    src: str
    dest_dir: str


class WorkspaceMoveIn(BaseModel):
    src: str
    dest: str


@router.post("/sessions/{session_id}/workspace/mkdir")
async def workspace_mkdir(session_id: str, user_id: str, body: WorkspaceMkdirIn) -> dict:
    from app.workspace.fs_ops import FsOpsError, mkdir

    uid = user_id.strip()
    sid = session_id.strip()
    try:
        return mkdir(uid, sid, body.path)
    except (WorkspaceError, FsOpsError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/sessions/{session_id}/workspace/copy")
async def workspace_copy(session_id: str, user_id: str, body: WorkspaceCopyIn) -> dict:
    from app.workspace.fs_ops import FsOpsError, copy_entry

    uid = user_id.strip()
    sid = session_id.strip()
    try:
        return copy_entry(uid, sid, body.src, body.dest_dir)
    except (WorkspaceError, FsOpsError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/sessions/{session_id}/workspace/move")
async def workspace_move(session_id: str, user_id: str, body: WorkspaceMoveIn) -> dict:
    from app.workspace.fs_ops import FsOpsError, move_entry

    uid = user_id.strip()
    sid = session_id.strip()
    try:
        return move_entry(uid, sid, body.src, body.dest)
    except (WorkspaceError, FsOpsError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/sessions/{session_id}/workspace/entry")
async def workspace_delete_entry(session_id: str, user_id: str, path: str) -> dict:
    from app.workspace.fs_ops import FsOpsError, delete_entry

    uid = user_id.strip()
    sid = session_id.strip()
    if not path.strip():
        raise HTTPException(status_code=400, detail="path required")
    try:
        return delete_entry(uid, sid, path)
    except (WorkspaceError, FsOpsError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
