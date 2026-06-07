from __future__ import annotations

import math
import time
from typing import Any

from parlant.client import GatewayTimeoutError, ParlantClient


def event_to_dict(event: Any) -> dict[str, Any]:
    if hasattr(event, "model_dump"):
        return event.model_dump()
    if isinstance(event, dict):
        return event
    return {k: getattr(event, k) for k in dir(event) if not k.startswith("_") and not callable(getattr(event, k))}


def event_offset(event: Any) -> int:
    try:
        return int(getattr(event, "offset"))
    except Exception:
        data = event_to_dict(event)
        try:
            return int(data.get("offset", -1))
        except Exception:
            return -1


def event_kind(event: Any) -> str:
    return str(getattr(event, "kind", event_to_dict(event).get("kind", "")))


def event_source(event: Any) -> str:
    return str(getattr(event, "source", event_to_dict(event).get("source", "")))


def event_trace_id(event: Any) -> str:
    data = event_to_dict(event)
    return str(data.get("trace_id") or data.get("correlation_id") or "")


def status_payload(event: Any) -> tuple[str, str]:
    if event_kind(event) != "status":
        return "", ""
    data = event_to_dict(event).get("data")
    if not isinstance(data, dict):
        return "", ""
    status = str(data.get("status") or "")
    inner = data.get("data") or {}
    stage = str(inner.get("stage") or "") if isinstance(inner, dict) else ""
    return status, stage


def event_message(event: Any) -> str | None:
    if event_kind(event) != "message":
        return None
    data = event_to_dict(event).get("data")
    if hasattr(data, "model_dump"):
        data = data.model_dump()
    if isinstance(data, dict):
        msg = data.get("message")
        return str(msg).strip() if isinstance(msg, str) and msg.strip() else None
    msg = getattr(data, "message", None)
    return str(msg).strip() if isinstance(msg, str) and msg.strip() else None


def wait_agent_reply(
    pc: ParlantClient,
    session_id: str,
    *,
    since_offset: int,
    expected_trace_id: str,
    poll_interval: float,
    max_turn_wait_sec: float,
    seen_offsets: set[int],
) -> tuple[str, int, dict[str, Any]]:
    """Wait until Parlant marks the customer trace ready/completed with agent text."""
    agent_texts: list[str] = []
    latest_offset = since_offset
    agent_count = 0
    accepted_by = ""
    completed_by_status = False
    timed_out = False
    response_started_at = time.monotonic()
    wait_for_data = max(1, math.ceil(poll_interval))

    while True:
        try:
            events = pc.sessions.list_events(
                session_id,
                min_offset=latest_offset + 1,
                wait_for_data=wait_for_data,
            )
        except GatewayTimeoutError:
            events = []
        for event in events:
            off = event_offset(event)
            latest_offset = max(latest_offset, off)
            if off in seen_offsets or off <= since_offset:
                continue
            seen_offsets.add(off)
            trace_id = event_trace_id(event)
            msg = event_message(event)
            src = event_source(event)
            status, stage = status_payload(event)
            if trace_id == expected_trace_id and status == "ready" and stage == "completed" and agent_count > 0:
                completed_by_status = True
            if msg and src == "ai_agent":
                agent_count += 1
                agent_texts.append(msg)
        if completed_by_status:
            accepted_by = "status_ready_completed"
            break
        if time.monotonic() - response_started_at >= max_turn_wait_sec:
            accepted_by = "max_turn_wait_without_completed"
            timed_out = True
            break
        time.sleep(poll_interval)

    text = "\n".join(agent_texts).strip() or ("（超时无回复）" if timed_out else "（无经纪人文本）")
    latency_ms = round((time.monotonic() - response_started_at) * 1000, 2)
    return text, latest_offset, {
        "agent_messages": agent_count,
        "accepted_by": accepted_by,
        "timed_out": timed_out,
        "latency_ms": latency_ms,
    }
