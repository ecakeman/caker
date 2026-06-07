from __future__ import annotations

from typing import Any


def build_matcher_evidence_projection(
    *,
    user_message: str,
    active_journey_id: str | None,
    active_state_id: str | None,
    recent_messages: list[str] | None = None,
    tool_results: list[dict[str, Any]] | None = None,
    state_markers: list[str] | None = None,
) -> str:
    """B4: compact structured evidence for matcher (no prompt blobs)."""
    parts: list[str] = [f"用户: {user_message.strip()[:400]}"]
    if active_journey_id:
        parts.append(f"active_journey={active_journey_id}")
    if active_state_id:
        parts.append(f"active_state={active_state_id}")
    for m in (state_markers or [])[:6]:
        parts.append(f"state_var={m}")
    for msg in (recent_messages or [])[-3:]:
        parts.append(f"recent: {msg[:120]}")
    for tr in (tool_results or [])[-2:]:
        name = tr.get("name") or tr.get("tool_id") or "tool"
        ok = tr.get("ok", tr.get("success", True))
        parts.append(f"tool_result {name} ok={ok}")
    return "\n".join(parts)
