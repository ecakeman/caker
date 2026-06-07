"""Structured observability event contract (broker-parity for parlant customer_sim)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

OBS_SCHEMA_VERSION = "1"

ERROR_CODES = {
    "SCHEMA_FORMAT_RETRY": "SCHEMA_FORMAT_RETRY",
    "SCHEMA_FAILED_MAX_ATTEMPTS": "SCHEMA_FAILED_MAX_ATTEMPTS",
    "OPENAI_CLIENT_RETRY": "OPENAI_CLIENT_RETRY",
    "SCHEMA_ATTEMPT_USAGE": "SCHEMA_ATTEMPT_USAGE",
    "SCHEMA_ATTEMPT_FAIL": "SCHEMA_ATTEMPT_FAIL",
    "NETWORK_RETRY_BACKOFF": "NETWORK_RETRY_BACKOFF",
    "SCHEMA_CALL_SUMMARY": "SCHEMA_CALL_SUMMARY",
    "UNKNOWN": "UNKNOWN",
}

EVENT_TYPES = {
    "run_manifest": "run_manifest",
    "session_event": "session_event",
    "dialogue_bubble": "dialogue_bubble",
    "turn_summary": "turn_summary",
    "gateway_log_signal": "gateway_log_signal",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _stage_from_event(ev: dict[str, Any]) -> str | None:
    if ev.get("kind") != "status":
        return None
    data = ev.get("data") or {}
    if not isinstance(data, dict):
        return None
    inner = data.get("data") or {}
    if isinstance(inner, dict):
        stage = inner.get("stage")
        if isinstance(stage, str) and stage.strip():
            return stage.strip()
    return None


def _status_name(ev: dict[str, Any]) -> str | None:
    if ev.get("kind") != "status":
        return None
    data = ev.get("data") or {}
    if not isinstance(data, dict):
        return None
    st = data.get("status")
    return str(st) if st is not None else None


def normalize_session_event_row(
    *,
    run_dir: str,
    session_id: str,
    turn: int | None,
    observed_at: str,
    event: dict[str, Any],
) -> dict[str, Any]:
    trace_id = str(event.get("trace_id") or event.get("correlation_id") or "")
    offset = event.get("offset")
    try:
        offset_i = int(offset) if offset is not None else None
    except (TypeError, ValueError):
        offset_i = None
    kind = str(event.get("kind") or "")
    source = str(event.get("source") or "")
    phase = _stage_from_event(event)
    status_name = _status_name(event)
    row: dict[str, Any] = {
        "ts": utc_now_iso(),
        "level": "info",
        "source": "customer_sim",
        "component": "session_sse",
        "session_id": session_id,
        "trace_id": trace_id,
        "offset": offset_i,
        "turn": turn,
        "kind": kind,
        "phase": phase,
        "status": status_name,
        "retry_count": None,
        "latency_ms": None,
        "error_code": None,
        "message": None,
        "event_type": EVENT_TYPES["session_event"],
        "schema_version": OBS_SCHEMA_VERSION,
        "run_dir": run_dir,
        "observed_at": observed_at,
    }
    if kind == "message":
        data = event.get("data") or {}
        if isinstance(data, dict):
            msg = data.get("message")
            if isinstance(msg, str):
                preview = msg[:500] + ("…" if len(msg) > 500 else "")
                row["message"] = preview
    elif kind == "tool":
        data = event.get("data") or {}
        if isinstance(data, dict):
            calls = data.get("tool_calls")
            if isinstance(calls, list) and calls:
                first = calls[0]
                if isinstance(first, dict):
                    tid = first.get("tool_id")
                    row["message"] = f"tool:{tid}"
    return row


_GATEWAY_RETRY_RE = re.compile(
    r"Format/schema error for (?P<schema>[^;]+);\s*retrying\s*\((?P<cur>\d+)/(?P<max>\d+)\)",
    re.I,
)
_GATEWAY_FAIL_RE = re.compile(
    r"does not match expected schema after (?P<n>\d+) attempts",
    re.I,
)


def parse_gateway_log_line(line: str) -> dict[str, Any] | None:
    """Extract retry/schema signals from raw gateway log lines (no broker OBS JSON)."""
    if "Format/schema error" in line and "retrying" in line:
        m = _GATEWAY_RETRY_RE.search(line)
        cur = int(m.group("cur")) if m else None
        mx = int(m.group("max")) if m else None
        schema = m.group("schema").strip() if m else None
        return {
            "event_type": EVENT_TYPES["gateway_log_signal"],
            "error_code": ERROR_CODES["SCHEMA_FORMAT_RETRY"],
            "message": line.strip()[:2000],
            "retry_count": cur,
            "phase": schema,
            "kind": "gateway_warning",
            "max_attempts_hint": mx,
        }
    if "does not match expected schema after" in line:
        m = _GATEWAY_FAIL_RE.search(line)
        n = int(m.group("n")) if m else None
        return {
            "event_type": EVENT_TYPES["gateway_log_signal"],
            "error_code": ERROR_CODES["SCHEMA_FAILED_MAX_ATTEMPTS"],
            "message": line.strip()[:2000],
            "retry_count": n,
            "kind": "gateway_error",
        }
    if "Retrying request to /chat/completions" in line:
        return {
            "event_type": EVENT_TYPES["gateway_log_signal"],
            "error_code": ERROR_CODES["OPENAI_CLIENT_RETRY"],
            "message": line.strip()[:500],
            "kind": "http_retry",
        }
    return None
