"""Broker-equivalent customer sim artifact builders (decoupled copy for parlant)."""

from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.log_paths import (
    gateway_process_root,
    gateway_session_messages_dir,
    parlant_home_resolved,
    project_root,
)


def int_offset(ev: dict[str, Any]) -> int:
    raw = ev.get("offset")
    if raw is None:
        return -1
    try:
        return int(raw)
    except (TypeError, ValueError):
        return -1


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return None


SIMULATION_SUBDIR = "simulation"
DIALOGUE_SUBDIR = "dialogue"
INSPECT_SUBDIR = "inspect"


@dataclass
class CustomerSimPaths:
    run_dir: Path
    simulation: Path = field(init=False)
    dialogue: Path = field(init=False)
    inspect: Path = field(init=False)

    def __post_init__(self) -> None:
        self.run_dir = self.run_dir.resolve()
        self.simulation = self.run_dir / SIMULATION_SUBDIR
        self.dialogue = self.run_dir / DIALOGUE_SUBDIR
        self.inspect = self.run_dir / INSPECT_SUBDIR

    def session_events(self) -> Path:
        canonical = self.inspect / "session_events.jsonl"
        if canonical.is_file():
            return canonical
        legacy = self.inspect / "events_raw.jsonl"
        if legacy.is_file():
            return legacy
        return self.run_dir / "events_raw.jsonl"

    def config_json(self) -> Path:
        p = self.simulation / "config.json"
        return p if p.is_file() else self.run_dir / "config.json"

    def session_json(self) -> Path:
        p = self.simulation / "session.json"
        return p if p.is_file() else self.run_dir / "session.json"

    def scenario_json(self) -> Path:
        p = self.simulation / "scenario.json"
        return p if p.is_file() else self.run_dir / "scenario.json"


def layout_paths(run_dir: Path) -> CustomerSimPaths:
    return CustomerSimPaths(run_dir=run_dir)


def load_events_raw_lines(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def event_id_from_dict(ev: dict[str, Any]) -> str:
    raw = ev.get("id")
    return str(raw) if raw is not None else ""


def trace_id_from_dict(ev: dict[str, Any]) -> str:
    raw = ev.get("trace_id") or ev.get("correlation_id")
    return str(raw) if raw is not None else ""


def tags_from_event(ev: dict[str, Any]) -> list[str]:
    meta = ev.get("metadata")
    if isinstance(meta, dict):
        tags = meta.get("tags")
        if isinstance(tags, list):
            return [str(x) for x in tags]
        if isinstance(tags, str) and tags.strip():
            return [tags.strip()]
    return []


def collect_gateway_log_paths(repo_root: Path | None = None) -> list[Path]:
    r = repo_root or project_root()
    paths: list[Path] = [
        gateway_process_root(r) / "gateway.log",
        parlant_home_resolved(r) / "parlant.log",
        r / "var" / "gateway" / "runtime" / "parlant.log",
        r / "var" / "runtime" / "parlant.log",
    ]
    out: list[Path] = []
    seen: set[str] = set()
    for p in paths:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def parse_log_timestamp(line: str) -> str | None:
    m = re.match(r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)", line)
    if m:
        return m.group(1).replace(" ", "T")
    return None


def parse_log_level(line: str) -> str | None:
    m = re.search(r"\b(DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|TRACE)\b", line)
    return m.group(1).upper() if m else None


def filter_runtime_logs_for_trace_ids(
    trace_ids: set[str],
    *,
    session_id: str | None = None,
    repo_root: Path | None = None,
    max_lines_per_file: int = 500_000,
) -> tuple[list[dict[str, Any]], list[str]]:
    notes: list[str] = []
    if not trace_ids:
        notes.append("no_trace_ids_from_events")
        return [], notes
    rows: list[dict[str, Any]] = []
    log_paths = collect_gateway_log_paths(repo_root)
    found_any_file = False
    for log_path in log_paths:
        if not log_path.is_file():
            notes.append(f"missing_file:{log_path}")
            continue
        found_any_file = True
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            notes.append(f"read_error:{log_path}:{exc}")
            continue
        n = 0
        for line in text.splitlines():
            if n >= max_lines_per_file:
                notes.append(f"truncated_after_lines:{log_path}:{max_lines_per_file}")
                break
            hit = next((t for t in trace_ids if t and t in line), None)
            if hit is None and session_id and session_id in line:
                hit = ""
            if hit is None:
                continue
            rows.append(
                {
                    "timestamp": parse_log_timestamp(line) or "",
                    "level": parse_log_level(line) or "",
                    "trace_id": hit,
                    "session_id": session_id or "",
                    "scope": "",
                    "message": line[:4000],
                    "source_file": str(log_path),
                }
            )
            n += 1
    if not found_any_file:
        notes.append("no_runtime_log_files_found")
    elif not rows:
        notes.append("no_matching_lines_for_trace_ids")
    return rows, notes


def _runtime_plaintext_dest_name(log_path: Path) -> str:
    low = log_path.name.lower()
    if low == "gateway.log":
        return "gateway_session.log"
    if "parlant" in low and low.endswith(".log"):
        return "parlant_session.log"
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", log_path.name)
    return f"runtime_{safe}"


def write_dialogue_session_runtime_plaintext(
    dialogue_dir: Path,
    trace_ids: set[str],
    session_id: str,
    *,
    repo_root: Path | None = None,
    max_lines_per_source: int = 500_000,
) -> dict[str, Any]:
    dialogue_dir.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    counts: dict[str, int] = {}
    dest_initialized: set[str] = set()

    def line_matches(line: str) -> bool:
        if trace_ids and any(t and t in line for t in trace_ids):
            return True
        return bool(session_id and session_id in line)

    for log_path in collect_gateway_log_paths(repo_root):
        if not log_path.is_file():
            notes.append(f"missing_file:{log_path}")
            continue
        dest_name = _runtime_plaintext_dest_name(log_path)
        out_path = dialogue_dir / dest_name
        append_mode = dest_name in dest_initialized
        try:
            infile = log_path.open("r", encoding="utf-8", errors="replace")
        except OSError as exc:
            notes.append(f"read_error:{log_path}:{exc}")
            continue
        n_written = 0
        pending_append_intro = ""
        if append_mode:
            pending_append_intro = f"\n# --- continued from {log_path} ---\n\n"
        try:
            with out_path.open("a" if append_mode else "w", encoding="utf-8") as outfile:
                if not append_mode:
                    outfile.write(
                        "# Verbatim process log lines for this session (trace_id or session_id match).\n"
                        f"# session_id={session_id}\n"
                        f"# source={log_path}\n\n"
                    )
                for raw_line in infile:
                    if n_written >= max_lines_per_source:
                        notes.append(f"truncated_after_lines:{log_path}:{max_lines_per_source}")
                        break
                    line = raw_line.rstrip("\n")
                    if not line_matches(line):
                        continue
                    if pending_append_intro:
                        outfile.write(pending_append_intro)
                        pending_append_intro = ""
                    outfile.write(raw_line if raw_line.endswith("\n") else raw_line + "\n")
                    n_written += 1
        finally:
            infile.close()
        counts[dest_name] = counts.get(dest_name, 0) + n_written
        if n_written == 0 and not append_mode:
            try:
                out_path.unlink(missing_ok=True)
            except OSError:
                pass
        elif n_written > 0:
            dest_initialized.add(dest_name)

    return {"dialogue_runtime_plain_files": counts, "dialogue_runtime_plain_notes": notes}


def copy_turn_pipeline_slice(
    session_id: str,
    run_dir: Path,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Copy session-scoped rows from global var/turn_pipeline.jsonl into the run dir."""
    from app.telemetry.writer import read_turn_records, turn_pipeline_path

    root = repo_root or project_root()
    src = turn_pipeline_path(root)
    telemetry_dir = run_dir / "telemetry"
    telemetry_dir.mkdir(parents=True, exist_ok=True)
    dst = telemetry_dir / "turn_pipeline.jsonl"
    rows = read_turn_records(src, session_id=session_id)
    if rows:
        with dst.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {
        "source": str(src),
        "destination": str(dst),
        "rows": len(rows),
        "bytes": int(dst.stat().st_size) if dst.is_file() else 0,
    }


def migrate_observability_events_to_dialogue(paths: CustomerSimPaths, *, dry_run: bool) -> str | None:
    legacy = paths.inspect / "observability_events.jsonl"
    modern = paths.dialogue / "observability_events.jsonl"
    if not legacy.is_file() or modern.is_file():
        return None
    if dry_run:
        return f"would_move->{modern.relative_to(paths.run_dir)}"
    paths.dialogue.mkdir(parents=True, exist_ok=True)
    shutil.move(str(legacy), str(modern))
    return f"moved_observability_events.jsonl->{modern.relative_to(paths.run_dir)}"


def infer_turn_by_offset_sequence(rows: list[dict[str, Any]]) -> dict[int, int]:
    order: list[dict[str, Any]] = []
    for row in rows:
        ev = row.get("event")
        if isinstance(ev, dict) and ev.get("offset") is not None:
            order.append(ev)
    order.sort(key=lambda e: int_offset(e))

    turn = 0
    offset_to_turn: dict[int, int] = {}
    for ev in order:
        off = int_offset(ev)
        if off < 0:
            continue
        if ev.get("kind") == "message" and ev.get("source") == "customer":
            turn += 1
        if turn == 0:
            turn = 1
        offset_to_turn[off] = turn
    return offset_to_turn


def message_from_event_dict(ev: dict[str, Any]) -> str | None:
    if ev.get("kind") != "message":
        return None
    data = ev.get("data")
    if isinstance(data, dict):
        msg = data.get("message")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()
    return None


def build_dialogue_normalized_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    offset_turn = infer_turn_by_offset_sequence(rows)
    records: list[dict[str, Any]] = []
    for row in rows:
        ev = row.get("event")
        if not isinstance(ev, dict):
            continue
        if ev.get("kind") != "message":
            continue
        src = str(ev.get("source") or "")
        if src not in ("customer", "ai_agent"):
            continue
        msg = message_from_event_dict(ev)
        if msg is None:
            continue
        off = int_offset(ev)
        ts = ""
        c = ev.get("creation_utc")
        if c:
            try:
                ts = datetime.fromisoformat(str(c).replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                ts = str(c)
        records.append(
            {
                "turn": offset_turn.get(off, 1),
                "offset": off,
                "event_id": event_id_from_dict(ev),
                "trace_id": trace_id_from_dict(ev),
                "source": src,
                "timestamp": ts,
                "message": msg,
                "tags": tags_from_event(ev),
            }
        )
    return records


def write_dialogue_normalized_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False, default=str) for r in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def build_dialogue_summary(
    rows: list[dict[str, Any]],
    *,
    messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if messages is None:
        messages = build_dialogue_normalized_records(rows)
    kinds: dict[str, int] = defaultdict(int)
    first_obs: str | None = None
    last_obs: str | None = None
    for row in rows:
        ev = row.get("event")
        if not isinstance(ev, dict):
            continue
        k = str(ev.get("kind") or "unknown")
        kinds[k] += 1
        oa = str(row.get("observed_at") or "")
        if oa:
            if first_obs is None or oa < first_obs:
                first_obs = oa
            if last_obs is None or oa > last_obs:
                last_obs = oa
    turns = {int(m.get("turn") or 0) for m in messages}
    turns.discard(0)
    return {
        "turn_count": max(turns) if turns else 0,
        "turns_with_messages": len(turns),
        "message_bubbles": len(messages),
        "events_by_kind": dict(kinds),
        "first_observed_at": first_obs,
        "last_observed_at": last_obs,
        "missing": {
            "any_message_events": len(messages) == 0,
            "events_empty": len(rows) == 0,
        },
    }


def write_jsonl_records(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False, default=str) for r in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def collect_trace_ids(rows: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for row in rows:
        ev = row.get("event")
        if isinstance(ev, dict):
            t = trace_id_from_dict(ev)
            if t:
                out.add(t)
    return out


def extract_log_types(message: str) -> list[str]:
    tags = [m.group(1) for m in re.finditer(r"\[([^\]]+)\]", message)]
    if tags and tags[0].startswith("T+"):
        tags = tags[1:]
    if tags and re.fullmatch(r"[0-9a-fA-F-]{16,}", tags[0] or ""):
        tags = tags[1:]
    return tags


def build_engine_traces_from_runtime_logs(runtime_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in runtime_rows:
        msg = str(row.get("message") or "")
        out.append(
            {
                "source_channel": "/logs",
                "timestamp": str(row.get("timestamp") or ""),
                "level": str(row.get("level") or ""),
                "trace_id": str(row.get("trace_id") or ""),
                "types": extract_log_types(msg),
                "message": msg,
                "source_file": str(row.get("source_file") or ""),
            }
        )
    return out


def format_annotated_dialogue_line(item: dict[str, Any]) -> list[str]:
    source = str(item.get("source") or "")
    turn = int(item.get("turn") or 0)
    timestamp = str(item.get("timestamp") or item.get("observed_at") or "unknown")
    message = str(item.get("message") or "").replace("\r\n", "\n").strip()
    lines = message.splitlines() or ["（空）"]

    if source == "customer":
        label = f">>> 客户[{turn}]"
        comment = f"# 发送时间: {timestamp}"
    elif source == "ai_agent":
        label = "<<< 经纪人"
        comment = f"# 回复时间: {timestamp}"
    else:
        label = f"--- {source or 'unknown'}"
        comment = f"# 记录时间: {timestamp}"

    formatted = [f"{label}: {lines[0]}  {comment}"]
    formatted.extend(lines[1:])
    return formatted


def _init_dialogue_header(
    path: Path,
    *,
    base_url: str,
    agent_id: str,
    session_id: str,
    scenario_id: str,
    scenario_topic: str,
) -> None:
    header = "\n".join(
        [
            "# Customer simulation dialogue (live)",
            f"# started_at={now_iso()}",
            f"# run_dir={path.parent}",
            f"# base_url={base_url}",
            f"# agent_id={agent_id}",
            f"# session_id={session_id}",
            f"# scenario={scenario_id} {scenario_topic}",
            "# format: >>> / <<< lines with # 发送时间 / # 回复时间 on the first line of each bubble.",
            "",
            f"======== 第 1/1 轮开始 session={session_id} 题材={scenario_topic} ========",
            "",
        ]
    )
    path.write_text(header, encoding="utf-8")


def rebuild_dialogue_annotated_log(run_dir: Path) -> None:
    paths = layout_paths(run_dir)
    config = _read_json(paths.config_json()) or {}
    session = _read_json(paths.session_json()) or {}
    scenario = _read_json(paths.scenario_json()) or {}
    session_id = str(config.get("session_id") or session.get("id") or "unknown")
    base_url = str(config.get("base_url") or "http://127.0.0.1:8084")
    agent_id = str(config.get("agent_id") or session.get("agent_id") or "")
    scenario_id = str(scenario.get("id") or "unknown")
    scenario_topic = str(scenario.get("topic") or "")

    rows_in = load_events_raw_lines(paths.session_events())
    offset_turn = infer_turn_by_offset_sequence(rows_in)

    paths.dialogue.mkdir(parents=True, exist_ok=True)
    ann_path = paths.dialogue / "dialogue_annotated.log"
    _init_dialogue_header(
        ann_path,
        base_url=base_url,
        agent_id=agent_id,
        session_id=session_id,
        scenario_id=scenario_id,
        scenario_topic=scenario_topic,
    )

    for row in rows_in:
        ev = row.get("event")
        if not isinstance(ev, dict):
            continue
        if ev.get("kind") != "message":
            continue
        msg = message_from_event_dict(ev)
        if msg is None:
            continue
        off = int_offset(ev)
        turn = offset_turn.get(off, 1)
        src = ev.get("source")
        if src == "customer":
            sim_source = "customer"
        elif src == "ai_agent":
            sim_source = "ai_agent"
        else:
            sim_source = str(src or "unknown")
        ts = ""
        c = ev.get("creation_utc")
        if c:
            try:
                ts = datetime.fromisoformat(str(c).replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                ts = str(c)
        item = {
            "timestamp": ts,
            "observed_at": str(row.get("observed_at") or ""),
            "turn": turn,
            "source": sim_source,
            "message": msg,
            "offset": off,
        }
        lines = format_annotated_dialogue_line(item)
        with ann_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n\n")
            f.flush()

    with ann_path.open("a", encoding="utf-8") as f:
        f.write(f"\n# rebuilt_at={now_iso()}\n")


def _copy_if_absent(src: Path, dst: Path, *, dry_run: bool) -> bool:
    if not src.is_file() or dst.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        return True
    dst.write_bytes(src.read_bytes())
    return True


def migrate_run_tree_to_canonical(run_dir: Path, *, dry_run: bool) -> dict[str, list[str]]:
    run_dir = run_dir.resolve()
    paths = layout_paths(run_dir)
    sim, dlg, insp = paths.simulation, paths.dialogue, paths.inspect
    copied: list[str] = []

    pairs: list[tuple[Path, Path]] = [
        (run_dir / "scenario.json", sim / "scenario.json"),
        (run_dir / "config.json", sim / "config.json"),
        (run_dir / "session.json", sim / "session.json"),
        (run_dir / "transcript.jsonl", sim / "customer_messages.jsonl"),
        (run_dir / "events_raw.jsonl", insp / "session_events.jsonl"),
        (run_dir / "transcript.txt", dlg / "transcript.txt"),
        (run_dir / "dialogue_annotated.log", dlg / "dialogue_annotated.log"),
        (run_dir / "dialogue_normalized.jsonl", dlg / "dialogue.jsonl"),
        (insp / "events_raw.jsonl", insp / "session_events.jsonl"),
        (insp / "inspect_full.jsonl", insp / "engine_traces.jsonl"),
        (insp / "observability_events.jsonl", dlg / "observability_events.jsonl"),
    ]
    for src, dst in pairs:
        if _copy_if_absent(src, dst, dry_run=dry_run):
            copied.append(f"{src.name}->{dst.relative_to(run_dir)}")

    return {"copied": copied}


def write_run_meta(
    paths: CustomerSimPaths,
    *,
    session_id: str,
    base_url: str,
    extras: dict[str, Any] | None = None,
) -> Path:
    scenario = _read_json(paths.scenario_json()) or {}
    config = _read_json(paths.config_json()) or {}
    session = _read_json(paths.session_json()) or {}
    body: dict[str, Any] = {
        "generated_at": now_iso(),
        "run_dir": str(paths.run_dir),
        "session_id": session_id,
        "scenario": scenario,
        "config": config,
        "session": session,
        "inspect_source": {
            "chat_page": "/chat",
            "session_events_sse": f"{base_url.rstrip('/')}/sessions/{{session_id}}/events?sse=true&min_offset=...&wait_for_data=60",
            "message_event_sse": f"{base_url.rstrip('/')}/sessions/{{session_id}}/events/{{event_id}}?sse=true",
            "logs_websocket": f"{base_url.rstrip('/')}/logs",
            "fields_seen": [
                "trace_id",
                "level",
                "message",
                "types(tags)",
                "event.message/status/tool",
            ],
        },
        "artifacts": {},
    }
    for rel in (
        "simulation/scenario.json",
        "simulation/config.json",
        "simulation/session.json",
        "simulation/customer_messages.jsonl",
        "dialogue/dialogue_annotated.log",
        "dialogue/transcript.txt",
        "dialogue/dialogue.jsonl",
        "telemetry/turn_pipeline.jsonl",
        "dialogue/gateway_session.log",
        "dialogue/parlant_session.log",
        "inspect/session_events.jsonl",
        "inspect/engine_traces.jsonl",
        "inspect/runtime_logs.jsonl",
        "inspect/inspect_attempts.jsonl",
    ):
        p = paths.run_dir / rel
        if p.is_file():
            body["artifacts"][rel] = str(p.resolve())
    if extras:
        body.update(extras)
    out = paths.run_dir / "run_meta.json"
    out.write_text(json.dumps(body, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return out


def build_derived_customer_sim_artifacts(
    run_dir: Path,
    *,
    dry_run: bool = False,
    repo_root: Path | None = None,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Populate broker-equivalent artifacts from session events and runtime logs."""
    run_dir = run_dir.resolve()
    paths = layout_paths(run_dir)
    migrate_run_tree_to_canonical(run_dir, dry_run=dry_run)
    obs_migration_note = migrate_observability_events_to_dialogue(paths, dry_run=dry_run)

    rows = load_events_raw_lines(paths.session_events())
    config = _read_json(paths.config_json()) or {}
    session = _read_json(paths.session_json()) or {}
    session_id = str(config.get("session_id") or session.get("id") or "unknown")
    base_url = str(config.get("base_url") or "http://127.0.0.1:8084")

    norm_records = build_dialogue_normalized_records(rows)
    dialogue_summary = build_dialogue_summary(rows, messages=norm_records)

    trace_ids = collect_trace_ids(rows)
    runtime_rows, log_notes = filter_runtime_logs_for_trace_ids(
        trace_ids,
        session_id=session_id,
        repo_root=repo_root,
    )
    engine_rows = build_engine_traces_from_runtime_logs(runtime_rows)

    if dry_run:
        return {
            "session_id": session_id,
            "would_write": [
                "dialogue/dialogue.jsonl",
                "dialogue/dialogue_annotated.log",
                "dialogue/gateway_session.log",
                "dialogue/parlant_session.log",
                "dialogue/observability_events.jsonl",
                "inspect/engine_traces.jsonl",
                "inspect/runtime_logs.jsonl",
                "run_meta.json",
            ],
        }

    paths.dialogue.mkdir(parents=True, exist_ok=True)
    paths.inspect.mkdir(parents=True, exist_ok=True)
    plain_meta = write_dialogue_session_runtime_plaintext(
        paths.dialogue,
        trace_ids,
        session_id,
        repo_root=repo_root,
    )
    turn_pipeline_meta = copy_turn_pipeline_slice(session_id, paths.run_dir, repo_root=repo_root)
    write_dialogue_normalized_jsonl(paths.dialogue / "dialogue.jsonl", norm_records)
    write_jsonl_records(paths.inspect / "runtime_logs.jsonl", runtime_rows)
    write_jsonl_records(paths.inspect / "engine_traces.jsonl", engine_rows)
    if not engine_rows:
        write_jsonl_records(
            paths.inspect / "inspect_attempts.jsonl",
            [
                {
                    "status": "unavailable",
                    "reason": "no_logs_for_trace_ids",
                    "source_channel": "/logs",
                }
            ],
        )

    rebuild_dialogue_annotated_log(run_dir)
    run_meta_extras: dict[str, Any] = {
        "summary": {**(summary or {}), **dialogue_summary},
        "coverage": {
            "session_events": bool(rows),
            "engine_trace": "complete" if engine_rows else "unavailable",
            "runtime_logs": "complete" if runtime_rows else "unavailable",
        },
        "missing": {
            "runtime_logs_empty": len(runtime_rows) == 0,
            "runtime_log_notes": log_notes,
        },
        "dialogue_runtime_plain": plain_meta,
        "turn_pipeline": turn_pipeline_meta,
        "observability_migration": obs_migration_note,
    }
    write_run_meta(
        paths,
        session_id=session_id,
        base_url=base_url,
        extras=run_meta_extras,
    )

    return {
        "session_id": session_id,
        "dialogue_summary": dialogue_summary,
        "runtime_log_notes": log_notes,
        "dialogue_runtime_plain": plain_meta,
        "turn_pipeline": turn_pipeline_meta,
    }
