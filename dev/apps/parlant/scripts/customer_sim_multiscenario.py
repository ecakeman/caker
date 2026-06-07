#!/usr/bin/env python3
"""Scenario-bank customer sim — slim telemetry (content_record + summary.md)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from parlant.client import ParlantClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.artifacts import load_artifacts  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.log_paths import customer_sim_root  # noqa: E402
from app.sim.customer_voice import create_customer_client, generate_customer_message  # noqa: E402
from app.sim.gateway_loop import event_offset, event_to_dict, event_trace_id, wait_agent_reply  # noqa: E402
from app.sim.scenario_plan import build_scenario_turn_plan, load_scenarios  # noqa: E402
from app.telemetry.level import is_debug_telemetry  # noqa: E402
from app.telemetry.writer import (  # noqa: E402
    content_record_path,
    read_turn_records,
    turn_pipeline_path,
)


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def sync_content_records(
    run_dir: Path,
    *,
    session_id: str,
    scenario_id: str,
    seen_turns: set[int],
) -> int:
    """Copy new global compact records into run_dir/records/content_record.jsonl."""
    global_rows = read_turn_records(content_record_path(ROOT), session_id=session_id)
    out = run_dir / "records" / "content_record.jsonl"
    added = 0
    for row in global_rows:
        turn = int(row.get("turn") or 0)
        if turn in seen_turns:
            continue
        seen_turns.add(turn)
        row = dict(row)
        row["run_id"] = run_dir.name
        row["scenario_id"] = scenario_id
        append_jsonl(out, row)
        added += 1
    return added


def write_debug_slice(run_dir: Path, *, session_id: str) -> None:
    if not is_debug_telemetry():
        return
    rows = read_turn_records(turn_pipeline_path(ROOT), session_id=session_id)
    if not rows:
        return
    dst = run_dir / "debug" / "turn_pipeline_full.jsonl"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def build_summary(run_dir: Path) -> None:
    script = ROOT / "scripts" / "build_sim_summary.py"
    py = ROOT / ".venv" / "bin" / "python3"
    if script.is_file() and py.is_file():
        subprocess.run([str(py), str(script), str(run_dir)], cwd=str(ROOT), check=False, timeout=60)


def create_customer_event_with_retry(
    pc: ParlantClient,
    session_id: str,
    *,
    message: str,
    attempts: int = 3,
) -> Any:
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return pc.sessions.create_event(session_id, kind="message", source="customer", message=message)
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            print(f"[create-event-retry] attempt={attempt} error={type(exc).__name__}", flush=True)
            time.sleep(2.0 * attempt)
    assert last_exc is not None
    raise last_exc


def sync_until_expected(
    run_dir: Path,
    *,
    session_id: str,
    scenario_id: str,
    seen_turns: set[int],
    expected_turns: int,
    timeout_sec: float = 15.0,
) -> None:
    deadline = time.monotonic() + timeout_sec
    while len(seen_turns) < expected_turns and time.monotonic() < deadline:
        sync_content_records(
            run_dir,
            session_id=session_id,
            scenario_id=scenario_id,
            seen_turns=seen_turns,
        )
        if len(seen_turns) >= expected_turns:
            return
        time.sleep(0.5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scenario-bank customer sim (slim telemetry)")
    parser.add_argument("--base-url", default=os.environ.get("PARLANT_BASE_URL", "http://127.0.0.1:8084"))
    parser.add_argument("--turns", type=int, default=20)
    parser.add_argument(
        "--scenario",
        default=os.environ.get("CUSTOMER_SIM_SCENARIO", "multiscenario"),
    )
    parser.add_argument("--agent-id", default=os.environ.get("PARLANT_AGENT_ID"))
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--max-turn-wait-sec", type=float, default=180.0)
    parser.add_argument("--llm-timeout-sec", type=float, default=60.0)
    parser.add_argument("--history-messages", type=int, default=8)
    parser.add_argument("--stop-after-tool", default=os.environ.get("CUSTOMER_SIM_STOP_AFTER_TOOL", ""))
    args = parser.parse_args()

    load_settings(ROOT)
    bundle = load_artifacts(load_settings(ROOT).artifacts_root)
    plan = build_scenario_turn_plan(bundle, scenario_id=args.scenario, turns=args.turns)

    primary_sid = args.scenario if args.scenario not in ("multiscenario", "multi") else "multiscenario"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = customer_sim_root(ROOT) / f"{stamp}_{primary_sid}"
    records_dir = run_dir / "records"
    records_dir.mkdir(parents=True, exist_ok=True)

    pc = ParlantClient(base_url=args.base_url)
    agents = pc.agents.list()
    agent_id = args.agent_id or (agents[0].id if agents else None)
    if not agent_id:
        raise SystemExit("no agent available on gateway")
    session = pc.sessions.create(agent_id=agent_id)
    session_id = session.id

    customer = create_customer_client(args.llm_timeout_sec)
    history: list[dict[str, str]] = []
    seen_offsets: set[int] = set()
    seen_turns: set[int] = set()
    latest_offset = -1
    prev_scenario_id: str | None = None

    for spec in plan:
        turn = int(spec["turn_index"])
        scenario = spec["scenario"]
        if prev_scenario_id and spec.get("scenario_id") != prev_scenario_id:
            history = []
        prev_scenario_id = str(spec.get("scenario_id") or "")

        seg_turn = int(spec["segment_turn"])
        seg_total = int(spec["segment_turns"])
        msg = generate_customer_message(
            customer,
            scenario=scenario,
            history=history,
            turn=seg_turn,
            total_turns=seg_total,
            history_messages=args.history_messages,
        )
        history.append({"role": "customer", "message": msg})

        since = latest_offset
        event = create_customer_event_with_retry(pc, session_id, message=msg)
        off = event_offset(event)
        latest_offset = max(latest_offset, off)
        seen_offsets.add(off)
        trace_id = event_trace_id(event) or str(event_to_dict(event).get("trace_id") or "")
        agent_text, latest_offset, meta = wait_agent_reply(
            pc,
            session_id,
            since_offset=since,
            expected_trace_id=trace_id,
            poll_interval=args.poll_interval,
            max_turn_wait_sec=args.max_turn_wait_sec,
            seen_offsets=seen_offsets,
        )
        history.append({"role": "ai_agent", "message": agent_text})

        time.sleep(1.0)
        sync_content_records(
            run_dir,
            session_id=session_id,
            scenario_id=str(spec.get("scenario_id") or ""),
            seen_turns=seen_turns,
        )
        if args.stop_after_tool:
            record_path = run_dir / "records" / "content_record.jsonl"
            if record_path.is_file():
                rows = [json.loads(l) for l in record_path.read_text(encoding="utf-8").splitlines() if l.strip()]
                if any(
                    t.get("name") == args.stop_after_tool
                    for r in rows
                    for t in (r.get("tools_called") or [])
                ):
                    print(f"[stop-after-tool] tool={args.stop_after_tool} triggered; stopping early", flush=True)
                    break
        print(
            f"[turn {turn:02d}] {spec.get('scenario_id')} latency_ms={meta.get('latency_ms')} "
            f"accepted_by={meta.get('accepted_by')}",
            flush=True,
        )
        time.sleep(0.3)

    time.sleep(2.0)
    sync_content_records(
        run_dir,
        session_id=session_id,
        scenario_id=str(plan[-1].get("scenario_id") or "") if plan else "",
        seen_turns=seen_turns,
    )
    sync_until_expected(
        run_dir,
        session_id=session_id,
        scenario_id=str(plan[-1].get("scenario_id") or "") if plan else "",
        seen_turns=seen_turns,
        expected_turns=len(plan),
    )
    write_debug_slice(run_dir, session_id=session_id)
    build_summary(run_dir)
    print(json.dumps({"run_dir": str(run_dir), "session_id": session_id}, ensure_ascii=False))


if __name__ == "__main__":
    main()
