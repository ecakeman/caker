from __future__ import annotations

import json
import re
import threading
import time
import uuid
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings
from app.workspace.manager import WorkspaceError, manager

_LOG_DIR = "logs"
_ENGINE_FILE = "engine.jsonl"
_SANDBOX_EXEC_FILE = "sandbox.exec.jsonl"
_SANDBOX_TERMINAL_FILE = "sandbox.terminal.log"
_SANDBOX_TERMINAL_TXT = "sandbox.terminal.txt"
_SANDBOX_CONTAINER_FILE = "sandbox.container.log"
_SANDBOX_CONTAINER_TXT = "sandbox.container.txt"
_SKILLS_FILE = "skills.jsonl"
_SANDBOX_LOG_FILE = "sandbox.log"
_AGENT_FILE = "agent.jsonl"

_TOKEN_COUNT_KEYS = frozenset(
    {
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "token_estimate",
        "token_source",
        "cost_usd",
    }
)

_SENSITIVE_KEY_RE = re.compile(
    r"(api[_-]?key|password|secret|authorization|access[_-]?token|refresh[_-]?token|auth[_-]?token)",
    re.I,
)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

_file_locks: dict[str, threading.Lock] = {}
_file_locks_guard = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _file_locks_guard:
        if key not in _file_locks:
            _file_locks[key] = threading.Lock()
        return _file_locks[key]


@dataclass(frozen=True)
class SessionLogContext:
    user_id: str
    session_id: str
    run_id: str = ""

    @classmethod
    def from_tool(cls, ctx: object) -> SessionLogContext:
        return cls(
            user_id=(getattr(ctx, "user_id", None) or "local").strip() or "local",
            session_id=(getattr(ctx, "session_id", None) or "demo").strip() or "demo",
        )

    @classmethod
    def from_ids(cls, user_id: str, session_id: str, *, run_id: str = "") -> SessionLogContext:
        return cls(
            user_id=(user_id or "local").strip() or "local",
            session_id=(session_id or "demo").strip() or "demo",
            run_id=run_id,
        )

    def with_run_id(self, run_id: str = "") -> SessionLogContext:
        """Return a copy with a new run_id (for paired tool_start/tool_end)."""
        return SessionLogContext(
            user_id=self.user_id,
            session_id=self.session_id,
            run_id=run_id or str(uuid.uuid4()),
        )


def log_for_context(ctx: object) -> SessionLogContext:
    return SessionLogContext.from_tool(ctx)


def log_for_ids(user_id: str, session_id: str, *, run_id: str = "") -> SessionLogContext:
    return SessionLogContext.from_ids(user_id, session_id, run_id=run_id)


def _logs_dir(user_id: str, session_id: str) -> Path:
    ws = manager.session_dir(user_id, session_id)
    log_root = ws / _LOG_DIR
    log_root.mkdir(parents=True, exist_ok=True)
    return log_root


def _is_sensitive_key(key: str) -> bool:
    if key in _TOKEN_COUNT_KEYS:
        return False
    return bool(_SENSITIVE_KEY_RE.search(key))


def _redact_value(key: str, value: Any) -> Any:
    if isinstance(value, str):
        if _is_sensitive_key(key):
            return "***"
        if len(value) > 2000:
            return value[:2000] + "…"
        return value
    if isinstance(value, dict):
        return {k: _redact_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(key, v) for v in value[:50]]
    return value


def _sanitize_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
    if not meta:
        return {}
    return {str(k): _redact_value(str(k), v) for k, v in meta.items()}


def _rotate_if_needed(path: Path) -> None:
    limit = settings.session_log_max_bytes
    if limit <= 0 or not path.is_file():
        return
    try:
        if path.stat().st_size < limit:
            return
    except OSError:
        return
    backup = path.with_suffix(path.suffix + ".1")
    try:
        if backup.is_file():
            backup.unlink()
        path.replace(backup)
    except OSError:
        pass


def _append_line(path: Path, record: dict[str, Any]) -> None:
    line = json.dumps(record, ensure_ascii=False) + "\n"
    lock = _lock_for(path)
    with lock:
        _rotate_if_needed(path)
        with path.open("a", encoding="utf-8") as f:
            f.write(line)


def append_jsonl(
    log_ctx: SessionLogContext,
    *,
    filename: str,
    source: str,
    event: str,
    msg: str,
    level: str = "INFO",
    meta: dict[str, Any] | None = None,
) -> None:
    if not settings.session_log_enabled:
        return
    if source == "agent" and not settings.session_agent_log_enabled:
        return
    try:
        log_dir = _logs_dir(log_ctx.user_id, log_ctx.session_id)
    except WorkspaceError:
        return

    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + f".{int(time.time() * 1000) % 1000:03d}Z",
        "source": source,
        "level": level,
        "event": event,
        "msg": msg,
        "meta": {
            "user_id": log_ctx.user_id,
            "session_id": log_ctx.session_id,
            "run_id": log_ctx.run_id or str(uuid.uuid4()),
            **_sanitize_meta(meta),
        },
    }
    _append_line(log_dir / filename, record)


def append_engine(
    log_ctx: SessionLogContext,
    event: str,
    msg: str,
    *,
    level: str = "INFO",
    meta: dict[str, Any] | None = None,
) -> None:
    append_jsonl(
        log_ctx,
        filename=_ENGINE_FILE,
        source="engine",
        event=event,
        msg=msg,
        level=level,
        meta=meta,
    )


def append_sandbox_exec(
    log_ctx: SessionLogContext,
    event: str,
    msg: str,
    *,
    level: str = "INFO",
    meta: dict[str, Any] | None = None,
) -> None:
    append_jsonl(
        log_ctx,
        filename=_SANDBOX_EXEC_FILE,
        source="sandbox",
        event=event,
        msg=msg,
        level=level,
        meta=meta,
    )


def append_skills(
    log_ctx: SessionLogContext,
    event: str,
    msg: str,
    *,
    level: str = "INFO",
    meta: dict[str, Any] | None = None,
) -> None:
    append_jsonl(
        log_ctx,
        filename=_SKILLS_FILE,
        source="skill",
        event=event,
        msg=msg,
        level=level,
        meta=meta,
    )


def append_agent(
    log_ctx: SessionLogContext,
    event: str,
    msg: str,
    *,
    level: str = "INFO",
    meta: dict[str, Any] | None = None,
) -> None:
    append_jsonl(
        log_ctx,
        filename=_AGENT_FILE,
        source="agent",
        event=event,
        msg=msg,
        level=level,
        meta=meta,
    )


def append_terminal_bytes(
    log_ctx: SessionLogContext,
    data: bytes,
    *,
    stream: str = "stdout",
) -> None:
    if not settings.session_log_enabled or not data:
        return
    try:
        log_dir = _logs_dir(log_ctx.user_id, log_ctx.session_id)
    except WorkspaceError:
        return
    path = log_dir / _SANDBOX_TERMINAL_FILE
    txt_path = log_dir / _SANDBOX_TERMINAL_TXT
    lock = _lock_for(path)
    with lock:
        _rotate_if_needed(path)
        _rotate_if_needed(txt_path)
        try:
            with path.open("ab") as f:
                if stream == "stdin":
                    f.write(b"[stdin] ")
                f.write(data)
        except OSError:
            return
        try:
            text = data.decode("utf-8", errors="replace")
            clean = strip_ansi_for_read(text)
            if stream == "stdin":
                clean = f"[stdin] {clean}"
            with txt_path.open("a", encoding="utf-8") as tf:
                tf.write(clean)
        except OSError:
            return


def append_container_bytes(log_ctx: SessionLogContext, data: bytes) -> None:
    if not settings.session_log_enabled or not data:
        return
    try:
        log_dir = _logs_dir(log_ctx.user_id, log_ctx.session_id)
    except WorkspaceError:
        return
    path = log_dir / _SANDBOX_CONTAINER_FILE
    txt_path = log_dir / _SANDBOX_CONTAINER_TXT
    lock = _lock_for(path)
    with lock:
        _rotate_if_needed(path)
        _rotate_if_needed(txt_path)
        try:
            with path.open("ab") as f:
                f.write(data)
        except OSError:
            return
        try:
            clean = strip_ansi_for_read(data.decode("utf-8", errors="replace"))
            with txt_path.open("a", encoding="utf-8") as tf:
                tf.write(clean)
        except OSError:
            return


def strip_ansi_for_read(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _utc_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def append_sandbox_log(log_ctx: SessionLogContext, text: str) -> None:
    if not settings.session_log_enabled or not text:
        return
    try:
        log_dir = _logs_dir(log_ctx.user_id, log_ctx.session_id)
    except WorkspaceError:
        return
    path = log_dir / _SANDBOX_LOG_FILE
    lock = _lock_for(path)
    with lock:
        _rotate_if_needed(path)
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(text)
                if not text.endswith("\n"):
                    f.write("\n")
        except OSError:
            return

