from __future__ import annotations

import hashlib
import re
import threading
from typing import Any

from app.config import settings
from app.observability.session_log import SessionLogContext
from app.workspace.manager import WorkspaceError, manager

_BLOB_DIR = "logs/blobs"
# engine log format v1.0 — tool_end preview max 200 chars; blob when > 1KB
TOOL_RESULT_PREVIEW_LEN = 200
TOOL_ARG_PREVIEW_LEN = 200
_SECRET_IN_TEXT_RE = re.compile(
    r"(sk-[a-zA-Z0-9]{20,}|api[_-]?key\s*[:=]\s*\S+|Bearer\s+\S+)",
    re.I,
)

_blob_locks: dict[str, threading.Lock] = {}
_blob_locks_guard = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    with _blob_locks_guard:
        if key not in _blob_locks:
            _blob_locks[key] = threading.Lock()
        return _blob_locks[key]


def redact_blob_text(text: str) -> str:
    return _SECRET_IN_TEXT_RE.sub("***", text)


def spill_if_large(
    log_ctx: SessionLogContext,
    text: str,
    *,
    label: str = "content",
    threshold: int | None = None,
    preview_len: int = TOOL_RESULT_PREVIEW_LEN,
) -> Any:
    """Return inline str (small), or {preview, len, sha256, ref?} for larger content."""
    t = "" if text is None else str(text)
    if len(t) <= preview_len:
        return t

    limit = threshold if threshold is not None else settings.session_log_blob_threshold
    digest = hashlib.sha256(t.encode("utf-8")).hexdigest()
    out: dict[str, Any] = {
        "preview": t[:preview_len] + "…",
        "len": len(t),
        "sha256": digest,
        "label": label,
    }
    if len(t) <= limit:
        return out

    rel = f"{_BLOB_DIR}/{digest[:16]}.txt"
    try:
        ws = manager.session_dir(log_ctx.user_id, log_ctx.session_id)
        blob_path = ws / rel
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        lock = _lock_for(rel)
        with lock:
            if not blob_path.is_file():
                blob_path.write_text(redact_blob_text(t), encoding="utf-8")
        out["ref"] = rel
    except (WorkspaceError, OSError):
        pass
    return out


def encode_value(log_ctx: SessionLogContext, value: Any) -> Any:
    if isinstance(value, str):
        return spill_if_large(log_ctx, value, label="arg", preview_len=TOOL_ARG_PREVIEW_LEN)
    if isinstance(value, dict):
        return {str(k): encode_value(log_ctx, v) for k, v in value.items()}
    if isinstance(value, list):
        return [encode_value(log_ctx, v) for v in value[:50]]
    return value


def encode_tool_result(log_ctx: SessionLogContext, text: str) -> dict[str, Any]:
    spilled = spill_if_large(
        log_ctx,
        text or "",
        label="result",
        preview_len=TOOL_RESULT_PREVIEW_LEN,
    )
    if isinstance(spilled, str):
        return {"preview": spilled}
    meta = dict(spilled)
    ref = meta.pop("ref", None)
    if ref:
        meta["result_ref"] = ref
    return meta


def preview_text(text: str, *, max_len: int = TOOL_RESULT_PREVIEW_LEN) -> str:
    t = (text or "").strip()
    if len(t) <= max_len:
        return t
    return t[:max_len] + "…"
