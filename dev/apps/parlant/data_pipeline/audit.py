from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from data_pipeline.ids import content_hash

HIGH_RISK_KEYWORDS = (
    "合规", "返佣", "投诉", "监管", "拒保", "健康告知", "如实告知",
    "诈骗", "误导", "违法", "隐私", "敏感",
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def audit_journey_graph(journey: dict[str, Any], ji: int) -> dict[str, Any]:
    title = journey.get("title") or f"journey_{ji}"
    states = {s["state_id"]: s for s in journey.get("states") or []}
    transitions = journey.get("transitions") or []
    issues: list[str] = []
    state_ids = set(states)
    for t in transitions:
        src, dst = t.get("from_state"), t.get("to_state")
        if src not in state_ids and src != "INITIAL":
            issues.append(f"missing from_state {src!r}")
        if dst not in state_ids and dst not in {"END"}:
            issues.append(f"missing to_state {dst!r}")
    reachable: set[str] = {"INITIAL"}
    changed = True
    while changed:
        changed = False
        for t in transitions:
            if t.get("from_state") in reachable:
                dst = t.get("to_state")
                if dst and dst not in reachable and dst != "END":
                    reachable.add(dst)
                    changed = True
    unreachable = sorted(state_ids - reachable)
    if unreachable:
        issues.append(f"unreachable states: {unreachable[:5]}")
    has_end = any(t.get("to_state") == "END" for t in transitions)
    if not has_end:
        issues.append("no END transition")
    conditional = [t for t in transitions if t.get("transition_kind") == "conditional"]
    return {
        "title": title,
        "state_count": len(states),
        "transition_count": len(transitions),
        "conditional_transition_count": len(conditional),
        "issues": issues,
    }


def _tokens(text: str) -> set[str]:
    text = text.lower()
    parts = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9_]{2,}", text))
    chars = [c for c in text if "\u4e00" <= c <= "\u9fff"]
    for i in range(len(chars) - 1):
        parts.add(chars[i] + chars[i + 1])
    return parts


def _find_similar_guidelines(guidelines: list[dict[str, Any]], threshold: float = 0.85) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for i in range(len(guidelines)):
        ti = _tokens(f"{guidelines[i].get('condition','')} {guidelines[i].get('action','')}")
        for j in range(i + 1, len(guidelines)):
            tj = _tokens(f"{guidelines[j].get('condition','')} {guidelines[j].get('action','')}")
            if not ti or not tj:
                continue
            score = len(ti & tj) / len(ti | tj)
            if score >= threshold:
                pairs.append({
                    "index_a": i,
                    "index_b": j,
                    "similarity": round(score, 3),
                    "condition_a": (guidelines[i].get("condition") or "")[:80],
                    "condition_b": (guidelines[j].get("condition") or "")[:80],
                })
    return pairs[:30]


def _find_duplicate_conditions(guidelines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_hash: dict[str, list[int]] = {}
    for i, g in enumerate(guidelines):
        h = content_hash(g.get("condition") or "")
        by_hash.setdefault(h, []).append(i)
    return [
        {"condition_hash": h, "indices": idxs, "condition": (guidelines[idxs[0]].get("condition") or "")[:100]}
        for h, idxs in by_hash.items()
        if len(idxs) > 1
    ]


def run_audit(guidelines_path: Path, journeys_path: Path) -> dict[str, Any]:
    guidelines = _load_json(guidelines_path)
    journeys = _load_json(journeys_path)
    tool_counts: Counter[str] = Counter()
    risk_hits: list[dict[str, str]] = []
    schema_issues: list[str] = []
    for i, g in enumerate(guidelines):
        for field in ("condition", "action"):
            if field not in g:
                schema_issues.append(f"guideline[{i}] missing {field}")
        for t in g.get("tools") or []:
            tool_counts[t] += 1
        text = f"{g.get('condition','')} {g.get('action','')}"
        for kw in HIGH_RISK_KEYWORDS:
            if kw in text:
                risk_hits.append({"keyword": kw, "condition": (g.get("condition") or "")[:120]})
                break
    for i, j in enumerate(journeys):
        for field in ("title", "states", "transitions"):
            if field not in j:
                schema_issues.append(f"journey[{i}] missing {field}")
    journey_reports = [audit_journey_graph(j, i) for i, j in enumerate(journeys)]
    journey_issues = sum(1 for r in journey_reports if r["issues"])
    return {
        "data_baseline": {
            "guideline_count": len(guidelines),
            "journey_count": len(journeys),
            "note": "项目书假设 450 guidelines / 6 journeys；当前原始数据以此为准",
        },
        "guideline_schema": {"fields": ["condition", "action", "tools"], "issues": schema_issues},
        "guideline_count": len(guidelines),
        "journey_count": len(journeys),
        "tool_distribution": dict(tool_counts),
        "duplicate_conditions": _find_duplicate_conditions(guidelines),
        "similar_guideline_pairs": _find_similar_guidelines(guidelines),
        "high_risk_guideline_hits": len(risk_hits),
        "high_risk_samples": risk_hits[:20],
        "journey_graph_issues": journey_issues,
        "journeys": journey_reports,
    }
