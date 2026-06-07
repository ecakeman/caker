from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.observability.schema import EVENT_TYPES, OBS_SCHEMA_VERSION, utc_now_iso


def inspect_dir(run_dir: Path) -> Path:
    p = run_dir / "inspect"
    p.mkdir(parents=True, exist_ok=True)
    return p


def dialogue_dir(run_dir: Path) -> Path:
    p = run_dir / "dialogue"
    p.mkdir(parents=True, exist_ok=True)
    return p


def init_observability_manifest(
    run_dir: Path,
    *,
    session_id: str,
    base_url: str,
    agent_id: str,
    scenario_id: str,
    scenario_topic: str,
    planned_turns: int,
) -> None:
    append_observability_event(
        run_dir,
        {
            "ts": utc_now_iso(),
            "level": "info",
            "source": "customer_sim",
            "component": "observability",
            "session_id": session_id,
            "trace_id": "",
            "offset": None,
            "turn": None,
            "kind": "manifest",
            "phase": None,
            "retry_count": None,
            "latency_ms": None,
            "error_code": None,
            "message": "observability manifest",
            "event_type": EVENT_TYPES["run_manifest"],
            "schema_version": OBS_SCHEMA_VERSION,
            "run_dir": str(run_dir.resolve()),
            "base_url": base_url,
            "agent_id": agent_id,
            "scenario_id": scenario_id,
            "scenario_topic": scenario_topic,
            "planned_turns": planned_turns,
            "otel_note": "Set OTEL_EXPORTER_OTLP_TRACES_ENDPOINT per "
            "https://www.parlant.io/docs/production/observability/ ; correlate via trace_id on events.",
        },
    )


def append_observability_event(run_dir: Path, event: dict[str, Any]) -> None:
    path = dialogue_dir(run_dir) / "observability_events.jsonl"
    if "ts" not in event:
        event = {**event, "ts": utc_now_iso()}
    if "schema_version" not in event:
        event = {**event, "schema_version": OBS_SCHEMA_VERSION}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        f.flush()


def append_dialogue_bubble_observability(
    run_dir: Path,
    *,
    session_id: str,
    turn: int,
    source: str,
    offset: int | None,
    timestamp: str,
    message_preview: str,
) -> None:
    append_observability_event(
        run_dir,
        {
            "level": "info",
            "source": "customer_sim",
            "component": "dialogue",
            "session_id": session_id,
            "trace_id": "",
            "offset": offset,
            "turn": turn,
            "kind": "message",
            "phase": None,
            "retry_count": None,
            "latency_ms": None,
            "error_code": None,
            "message": message_preview[:500],
            "event_type": EVENT_TYPES["dialogue_bubble"],
            "bubble_source": source,
            "bubble_timestamp": timestamp,
            "run_dir": str(run_dir.resolve()),
        },
    )


def append_turn_summary_observability(
    run_dir: Path,
    *,
    session_id: str,
    turn: int,
    agent_messages: int,
    timed_out: bool,
    accepted_by: str,
    latest_offset: int,
    latency_ms: int | None = None,
    total_turn_ms: int | None = None,
    history_chars_before: int | None = None,
    history_chars_after: int | None = None,
) -> None:
    append_observability_event(
        run_dir,
        {
            "level": "info",
            "source": "customer_sim",
            "component": "turn",
            "session_id": session_id,
            "trace_id": "",
            "offset": latest_offset,
            "turn": turn,
            "kind": "turn_summary",
            "phase": accepted_by,
            "retry_count": None,
            "latency_ms": latency_ms,
            "error_code": "REPLY_TIMEOUT" if timed_out else None,
            "message": f"agent_messages={agent_messages}",
            "event_type": EVENT_TYPES["turn_summary"],
            "timed_out": timed_out,
            "agent_messages": agent_messages,
            "total_turn_ms": total_turn_ms,
            "history_chars_before": history_chars_before,
            "history_chars_after": history_chars_after,
            "run_dir": str(run_dir.resolve()),
        },
    )
