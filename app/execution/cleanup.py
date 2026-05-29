from __future__ import annotations

import logging

from app.execution.docker_util import destroy_container, venue_container_name

logger = logging.getLogger(__name__)


def destroy_session_venue(user_id: str, session_id: str) -> None:
    """Remove Caker-managed venue shell container for a session."""
    destroy_container(venue_container_name(user_id, session_id))


def cleanup_orphan_containers() -> int:
    """Startup hook: reserved for future orphan venue cleanup."""
    return 0
