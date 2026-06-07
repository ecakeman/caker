from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _state_kind_map(journey: dict[str, Any]) -> dict[str, str]:
    return {s["state_id"]: s.get("state_kind", "chat_state") for s in journey.get("states") or []}


def audit_journey_governance(journey: dict[str, Any]) -> dict[str, Any]:
    kinds = _state_kind_map(journey)
    transitions = journey.get("transitions") or []
    issues: list[str] = []
    conditional_by_src: dict[str, list[str]] = {}
    for t in transitions:
        src = t.get("from_state")
        if t.get("transition_kind") == "conditional":
            conditional_by_src.setdefault(src, []).append(t.get("condition_text") or "")
        dst = t.get("to_state")
        if kinds.get(src) == "tool_state" and dst and dst != "END":
            if kinds.get(dst) != "chat_state":
                issues.append(f"tool_state {src!r} -> {dst!r} should be followed by chat_state")
    for src, conds in conditional_by_src.items():
        if len(conds) > 1 and len(set(conds)) < len(conds):
            issues.append(f"overlapping conditional transitions from {src!r}")
    return {
        "journey_id": journey.get("journey_id"),
        "title": journey.get("title"),
        "issues": issues,
    }


def journey_to_mermaid(journey: dict[str, Any]) -> str:
    lines = ["flowchart TD"]
    jid = journey.get("journey_id", "journey")
    for s in journey.get("states") or []:
        sid = s["state_id"]
        label = sid.replace('"', "'")
        kind = s.get("state_kind", "chat_state")
        shape = f'["{label}\\n({kind})"]' if kind == "chat_state" else f'[/"{label}\\n(tool)"/]'
        lines.append(f"  {jid}_{sid}{shape}")
    lines.append(f'  {jid}_INITIAL(["INITIAL"])')
    for t in journey.get("transitions") or []:
        src = f"{jid}_INITIAL" if t.get("from_state") == "INITIAL" else f"{jid}_{t.get('from_state')}"
        dst = "END_NODE" if t.get("to_state") == "END" else f"{jid}_{t.get('to_state')}"
        cond = (t.get("condition_text") or "").replace('"', "'")[:40]
        edge = f"  {src} -->|{cond}| {dst}" if cond else f"  {src} --> {dst}"
        lines.append(edge)
    lines.append('  END_NODE(["END"])')
    return "\n".join(lines)


def write_journey_artifacts(journeys: list[dict[str, Any]], out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    governance = [audit_journey_governance(j) for j in journeys]
    gov_path = out_dir / "journey_governance.json"
    gov_path.write_text(json.dumps(governance, ensure_ascii=False, indent=2), encoding="utf-8")
    mermaid_dir = out_dir / "mermaid"
    mermaid_dir.mkdir(exist_ok=True)
    for j in journeys:
        jid = j.get("journey_id", "unknown")
        (mermaid_dir / f"{jid}.mmd").write_text(journey_to_mermaid(j), encoding="utf-8")
    issue_count = sum(1 for g in governance if g["issues"])
    return {
        "journey_governance_path": str(gov_path),
        "mermaid_dir": str(mermaid_dir),
        "journeys_with_issues": issue_count,
    }
