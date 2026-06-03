from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.runtime.graph import get_graph
from app.user_profile.store import reflect_from_messages

logger = logging.getLogger(__name__)


async def schedule_profile_reflect(
    user_id: str,
    session_id: str,
    config: dict,
) -> None:
    if not settings.user_profile_enabled:
        return

    async def _run() -> None:
        try:
            snap = await get_graph().aget_state(config)
            values = snap.values if snap is not None else {}
            messages = (values or {}).get("messages") or []
            await asyncio.to_thread(reflect_from_messages, user_id, session_id, messages)
        except Exception:
            logger.exception("user profile reflect failed")

    asyncio.create_task(_run())
