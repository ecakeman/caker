from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any

_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class WebStoreError(Exception):
    pass


def _validate_id(value: str, label: str) -> str:
    v = value.strip()
    if not _ID_RE.fullmatch(v):
        raise WebStoreError(f"invalid {label}: {value}")
    return v


class WebDataStore:
    def __init__(self, root: str | Path = "var/web") -> None:
        self.root = Path(root)
        self.users_path = self.root / "users.json"
        self.settings_path = self.root / "settings.json"
        self.sessions_root = self.root / "sessions"

    def ensure_dirs(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.sessions_root.mkdir(parents=True, exist_ok=True)

    def _read_json(self, path: Path, default: Any) -> Any:
        if not path.is_file():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise WebStoreError(f"corrupt json: {path}") from e

    def _write_json(self, path: Path, data: Any) -> None:
        self.ensure_dirs()
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _session_path(self, user_id: str, session_id: str) -> Path:
        uid = _validate_id(user_id, "user_id")
        sid = _validate_id(session_id, "session_id")
        return self.sessions_root / uid / f"{sid}.json"

    def list_users(self) -> list[dict[str, Any]]:
        self.ensure_dirs()
        users = self._read_json(self.users_path, [])
        if not isinstance(users, list):
            return []
        return users

    def add_user(self, user_id: str) -> dict[str, Any]:
        uid = _validate_id(user_id, "user_id")
        users = self.list_users()
        if any(u.get("id") == uid for u in users):
            raise WebStoreError(f"user already exists: {uid}")
        entry = {"id": uid, "createdAt": int(time.time() * 1000)}
        users.append(entry)
        self._write_json(self.users_path, users)
        (self.sessions_root / uid).mkdir(parents=True, exist_ok=True)
        return entry

    def remove_user(self, user_id: str) -> None:
        uid = _validate_id(user_id, "user_id")
        users = [u for u in self.list_users() if u.get("id") != uid]
        self._write_json(self.users_path, users)
        user_dir = self.sessions_root / uid
        if user_dir.is_dir():
            shutil.rmtree(user_dir)
        settings = self.load_settings()
        active = settings.get("activeSessionByUser") or {}
        if isinstance(active, dict) and uid in active:
            active = {k: v for k, v in active.items() if k != uid}
            settings["activeSessionByUser"] = active
            if settings.get("activeUserId") == uid:
                settings["activeUserId"] = users[0]["id"] if users else "local"
            self.save_settings(settings)

    def ensure_default_user(self) -> None:
        users = self.list_users()
        if users:
            return
        self.add_user("local")

    def load_settings(self) -> dict[str, Any]:
        self.ensure_dirs()
        default = {
            "activeUserId": "local",
            "streaming": True,
            "theme": "system",
            "activeSessionByUser": {},
        }
        raw = self._read_json(self.settings_path, default)
        if not isinstance(raw, dict):
            return default
        out = {
            "activeUserId": raw.get("activeUserId") or "local",
            "streaming": raw.get("streaming", True) is not False,
            "theme": raw.get("theme") or "system",
            "activeSessionByUser": raw.get("activeSessionByUser") or {},
        }
        if isinstance(raw.get("llmByUser"), dict):
            out["llmByUser"] = raw["llmByUser"]
        return out

    def save_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        cur = self.load_settings()
        cur.update(patch)
        self._write_json(self.settings_path, cur)
        return cur

    def list_sessions(self, user_id: str) -> list[dict[str, Any]]:
        uid = _validate_id(user_id, "user_id")
        user_dir = self.sessions_root / uid
        if not user_dir.is_dir():
            return []
        out: list[dict[str, Any]] = []
        for path in user_dir.glob("*.json"):
            try:
                data = self._read_json(path, None)
            except WebStoreError:
                continue
            if not isinstance(data, dict):
                continue
            out.append(
                {
                    "id": data.get("id", path.stem),
                    "title": data.get("title", "新对话"),
                    "userId": data.get("userId", uid),
                    "updatedAt": data.get("updatedAt", 0),
                }
            )
        out.sort(key=lambda x: x.get("updatedAt", 0), reverse=True)
        return out

    def list_session_ids(self, user_id: str) -> list[str]:
        return [s["id"] for s in self.list_sessions(user_id)]

    def get_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        path = self._session_path(user_id, session_id)
        if not path.is_file():
            return None
        data = self._read_json(path, None)
        if not isinstance(data, dict):
            return None
        return data

    def save_session(self, session: dict[str, Any]) -> dict[str, Any]:
        user_id = str(session.get("userId") or "local")
        session_id = str(session.get("id") or "")
        if not session_id:
            raise WebStoreError("session id required")
        uid = _validate_id(user_id, "user_id")
        sid = _validate_id(session_id, "session_id")
        session = {
            **session,
            "id": sid,
            "userId": uid,
            "updatedAt": int(time.time() * 1000),
            "messages": session.get("messages") or [],
        }
        path = self._session_path(uid, sid)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_json(path, session)
        return session

    def create_session(self, user_id: str, session_id: str | None = None) -> dict[str, Any]:
        import uuid

        uid = _validate_id(user_id, "user_id")
        sid = _validate_id(session_id or f"chat-{uuid.uuid4()}", "session_id")
        session = {
            "id": sid,
            "title": "新对话",
            "userId": uid,
            "updatedAt": int(time.time() * 1000),
            "messages": [],
        }
        return self.save_session(session)

    def delete_session(self, user_id: str, session_id: str) -> None:
        path = self._session_path(user_id, session_id)
        if path.is_file():
            path.unlink()

    def delete_all_sessions_for_user(self, user_id: str) -> None:
        uid = _validate_id(user_id, "user_id")
        user_dir = self.sessions_root / uid
        if user_dir.is_dir():
            shutil.rmtree(user_dir)

    def import_legacy(self, payload: dict[str, Any]) -> dict[str, int]:
        """一次性从浏览器 localStorage 导入。"""
        counts = {"users": 0, "sessions": 0}
        users = payload.get("users") or []
        if isinstance(users, list):
            existing = {u.get("id") for u in self.list_users()}
            for u in users:
                if not isinstance(u, dict):
                    continue
                uid = str(u.get("id") or "").strip()
                if not uid or uid in existing:
                    continue
                try:
                    self.add_user(uid)
                    existing.add(uid)
                    counts["users"] += 1
                except WebStoreError:
                    pass

        sessions = payload.get("sessions") or []
        if isinstance(sessions, list):
            for s in sessions:
                if not isinstance(s, dict) or not s.get("id"):
                    continue
                try:
                    self.save_session(s)
                    counts["sessions"] += 1
                except WebStoreError:
                    pass

        settings = payload.get("settings")
        if isinstance(settings, dict):
            self.save_settings(
                {
                    k: settings[k]
                    for k in ("activeUserId", "streaming", "theme", "activeSessionByUser")
                    if k in settings
                }
            )

        return counts


store = WebDataStore()
