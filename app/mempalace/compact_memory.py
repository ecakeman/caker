from __future__ import annotations

import logging
import time
import uuid

from app.config import settings
from app.mempalace.chroma_store import add
from app.observability.session_log import append_engine, log_for_ids

logger = logging.getLogger(__name__)

_MEMORY_PREFIX = "会话上下文压缩（供后续跨会话召回）"


def format_compact_memory_document(
    summary_text: str,
    *,
    user_id: str,
    session_id: str,
) -> str:
    body = (summary_text or "").strip()
    return (
        f"{_MEMORY_PREFIX}\n"
        f"用户: {user_id}\n"
        f"会话: {session_id}\n\n"
        f"{body}"
    )


def persist_compact_summary(
    summary_text: str,
    *,
    user_id: str,
    session_id: str,
) -> str | None:
    """
    Store compact summary in Chroma long-term memory (best-effort).
    Returns memory_id on success, None if skipped or failed.
    """
    if not settings.mempalace_compact_persist:
        return None
    body = (summary_text or "").strip()
    if not body:
        return None

    uid = (user_id or "local").strip() or "local"
    sid = (session_id or "demo").strip() or "demo"
    memory_id = uuid.uuid4().hex
    metadata = {
        "user_id": uid,
        "session_id": sid,
        "source": "compact",
        "created_at": int(time.time() * 1000),
    }
    document = format_compact_memory_document(body, user_id=uid, session_id=sid)
    try:
        add(memory_id, document, metadata)
    except Exception as e:
        logger.warning(
            "compact summary not persisted to chroma (user=%s session=%s): %s",
            uid,
            sid,
            e,
        )
        append_engine(
            log_for_ids(uid, sid),
            "mempalace_compact_persist",
            "failed",
            level="ERROR",
            meta={"memory_id": memory_id, "error": str(e)},
        )
        return None
    logger.info(
        "compact summary persisted to chroma memory_id=%s user=%s session=%s",
        memory_id,
        uid,
        sid,
    )
    append_engine(
        log_for_ids(uid, sid),
        "mempalace_compact_persist",
        "stored",
        meta={"memory_id": memory_id, "summary_len": len(body)},
    )
    return memory_id
