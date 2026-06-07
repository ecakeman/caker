from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _topic_tags(text: str) -> set[str]:
    tags: set[str] = set()
    mapping = {
        "重疾": "critical_illness",
        "医疗": "medical",
        "核保": "underwriting",
        "理赔": "claims",
        "停售": "urgency",
        "返佣": "compliance",
        "合规": "compliance",
        "健康告知": "disclosure",
        "少儿": "child",
        "意外": "accident",
    }
    for k, v in mapping.items():
        if k in text:
            tags.add(v)
    return tags


def _broker_id_map(guidelines: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for g in guidelines:
        bid = g.get("broker_source_id")
        if bid:
            out[str(bid)] = g["guideline_id"]
    return out


def _load_raw_relations(path: Path | None) -> list[dict[str, Any]]:
    if not path or not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("relations") or [])


def extract_relationships(
    guidelines: list[dict[str, Any]],
    *,
    raw_relations_path: Path | None = None,
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    by_tag: dict[str, list[str]] = {}
    compliance_ids: list[str] = []
    promo_ids: list[str] = []
    broker_map = _broker_id_map(guidelines)

    for g in guidelines:
        gid = g["guideline_id"]
        text = f"{g['condition_text']} {g['action_text']}"
        tags = _topic_tags(text)
        for t in tags:
            by_tag.setdefault(t, []).append(gid)
        if g.get("risk_level") == "high" or "合规" in text or "返佣" in text:
            compliance_ids.append(gid)
        if any(k in text for k in ("停售", "促单", "紧迫感", "涨价")):
            promo_ids.append(gid)

    for cid in compliance_ids:
        for pid in promo_ids:
            edges.append({
                "type": "exclusion",
                "source_id": cid,
                "target_id": pid,
                "reason": "compliance_over_promo",
                "confidence": 0.85,
                "inference": "heuristic_risk_vs_promo",
            })

    for tag, ids in by_tag.items():
        if len(ids) < 2:
            continue
        base = min(ids)
        for other in ids:
            if other == base:
                continue
            cond = next(g["condition_text"] for g in guidelines if g["guideline_id"] == other)
            if "科普" in cond or "解释" in cond or "辨析" in cond:
                edges.append({
                    "type": "dependency",
                    "source_id": other,
                    "target_id": base,
                    "reason": f"topic_{tag}_baseline",
                    "confidence": 0.7,
                    "inference": "heuristic_topic_baseline",
                })
                edges.append({
                    "type": "entailment",
                    "source_id": base,
                    "target_id": other,
                    "reason": f"baseline_entails_detail_{tag}",
                    "confidence": 0.65,
                    "inference": "derived_from_dependency",
                })

    for rel in _load_raw_relations(raw_relations_path):
        rtype = str(rel.get("type") or "priority")
        src_b = str(rel.get("source") or "")
        tgt_b = str(rel.get("target") or "")
        src = broker_map.get(src_b)
        tgt = broker_map.get(tgt_b)
        if not src or not tgt:
            continue
        edges.append({
            "type": rtype,
            "source_id": src,
            "target_id": tgt,
            "reason": rel.get("rationale") or "broker_relations_json",
            "confidence": 0.9,
            "inference": "raw_relations_json",
            "broker_source": src_b,
            "broker_target": tgt_b,
        })

    disambig_tags = [t for t, ids in by_tag.items() if t in {"critical_illness", "medical", "accident"} and len(ids) >= 2]
    if len(disambig_tags) >= 2:
        target_ids = []
        for tag in disambig_tags:
            target_ids.extend(by_tag[tag][:3])
        edges.append({
            "type": "disambiguation",
            "source_id": "obs_product_intent_ambiguous",
            "target_ids": sorted(set(target_ids))[:8],
            "reason": "multi_product_intent",
            "confidence": 0.75,
            "inference": "heuristic_multi_product",
        })

    seen: set[tuple[Any, ...]] = set()
    deduped: list[dict[str, Any]] = []
    for e in edges:
        key = (
            e["type"],
            e.get("source_id"),
            e.get("target_id"),
            tuple(e.get("target_ids") or ()),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    return deduped


def detect_relationship_cycles(edges: list[dict[str, Any]]) -> list[list[str]]:
    """A4: directed cycle detection on entailment/dependency edges."""
    graph: dict[str, list[str]] = {}
    for e in edges:
        if e.get("type") not in {"entailment", "dependency"}:
            continue
        src = e.get("source_id")
        tgt = e.get("target_id")
        if src and tgt:
            graph.setdefault(str(src), []).append(str(tgt))

    cycles: list[list[str]] = []
    visited: set[str] = set()
    stack: set[str] = set()
    path: list[str] = []

    def dfs(node: str) -> None:
        visited.add(node)
        stack.add(node)
        path.append(node)
        for nxt in graph.get(node, []):
            if nxt not in visited:
                dfs(nxt)
            elif nxt in stack:
                idx = path.index(nxt)
                cycles.append(path[idx:] + [nxt])
        path.pop()
        stack.remove(node)

    for node in graph:
        if node not in visited:
            dfs(node)
    return cycles


def _break_cycles(edges: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    cleaned = list(edges)
    removed = 0
    for _ in range(8):
        cycles = detect_relationship_cycles(cleaned)
        if not cycles:
            break
        cycle = cycles[0]
        if len(cycle) < 2:
            break
        a, b = cycle[0], cycle[1]
        candidates = [
            e
            for e in cleaned
            if e.get("type") in {"entailment", "dependency"}
            and str(e.get("source_id")) == a
            and str(e.get("target_id")) == b
        ]
        if not candidates:
            break
        drop = min(candidates, key=lambda e: float(e.get("confidence") or 0))
        cleaned = [e for e in cleaned if e is not drop]
        removed += 1
    return cleaned, removed


def write_relationships(
    guidelines_path: Path,
    out_path: Path,
    *,
    raw_relations_path: Path | None = None,
) -> dict[str, Any]:
    guidelines = json.loads(guidelines_path.read_text(encoding="utf-8"))
    edges = extract_relationships(guidelines, raw_relations_path=raw_relations_path)
    edges, removed_edges = _break_cycles(edges)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cycles = detect_relationship_cycles(edges)
    out_path.write_text(json.dumps(edges, ensure_ascii=False, indent=2), encoding="utf-8")
    cycle_report = out_path.parent / "reports" / "relationship_cycles.json"
    cycle_report.parent.mkdir(parents=True, exist_ok=True)
    cycle_report.write_text(
        json.dumps(
            {
                "relationship_cycle_count": len(cycles),
                "cycles": cycles[:20],
                "edges_removed_for_cycle_break": removed_edges,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    by_type: dict[str, int] = {}
    for e in edges:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
    return {
        "relationships_path": str(out_path),
        "edge_count": len(edges),
        "by_type": by_type,
        "relationship_cycle_count": len(cycles),
        "cycle_edges_removed": removed_edges,
    }
