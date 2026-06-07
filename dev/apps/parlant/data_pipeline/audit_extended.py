from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _detect_cycles(edges: list[dict[str, Any]]) -> list[list[str]]:
    graph: dict[str, list[str]] = {}
    for e in edges:
        if e.get("type") not in {"dependency", "entailment", "priority"}:
            continue
        src, tgt = e.get("source_id"), e.get("target_id")
        if src and tgt:
            graph.setdefault(str(src), []).append(str(tgt))
    cycles: list[list[str]] = []
    visited: set[str] = set()
    stack: set[str] = set()
    path: list[str] = []

    def dfs(node: str) -> None:
        if node in stack:
            if node in path:
                i = path.index(node)
                cycles.append(path[i:] + [node])
            return
        if node in visited:
            return
        visited.add(node)
        stack.add(node)
        path.append(node)
        for nxt in graph.get(node, []):
            dfs(nxt)
        path.pop()
        stack.discard(node)

    for n in graph:
        dfs(n)
    return cycles[:10]


def run_extended_audit(
    *,
    guidelines_path: Path,
    journeys_path: Path,
    scope_path: Path,
    relationships_path: Path,
    variables_path: Path,
    index_records_path: Path,
    corpus_path: Path,
) -> dict[str, Any]:
    guidelines = _load_json(guidelines_path)
    journeys = _load_json(journeys_path)
    scope = _load_json(scope_path)
    relationships = _load_json(relationships_path)
    variables = _load_json(variables_path)

    gid_set = {g["guideline_id"] for g in guidelines}
    scoped_ids: set[str] = set(scope.get("always_on") or [])
    scoped_ids.update(scope.get("global") or [])
    for ids in (scope.get("journey_scoped") or {}).values():
        scoped_ids.update(ids)
    for ids in (scope.get("state_scoped") or {}).values():
        scoped_ids.update(ids)
    unscoped = sorted(gid_set - scoped_ids)

    index_ids = set()
    if index_records_path.is_file():
        for line in index_records_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                index_ids.add(json.loads(line)["guideline_id"])
    corpus_ids = set()
    if corpus_path.is_file():
        for line in corpus_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                corpus_ids.add(json.loads(line)["guideline_id"])

    rel_missing = []
    for e in relationships:
        for field in ("source_id", "target_id"):
            val = e.get(field)
            if val and val not in gid_set and not str(val).startswith("obs_"):
                rel_missing.append({field: val, "type": e.get("type")})

    by_journey_states = {
        j["journey_id"]: len(j.get("states") or [])
        for j in journeys
    }
    state_buckets = scope.get("state_scoped") or {}

    return {
        "scope_coverage": {
            "guideline_total": len(gid_set),
            "scoped_total": len(scoped_ids),
            "unscoped_guideline_ids": unscoped[:20],
            "unscoped_count": len(unscoped),
            "state_buckets": len(state_buckets),
            "state_unknown_flagged": bool((scope.get("fallback_rules") or {}).get("unknown_state_scope", {}).get("active")),
        },
        "relationship_graph": {
            "edge_count": len(relationships),
            "by_type": _count_by_type(relationships),
            "dangling_refs": rel_missing[:20],
            "cycle_samples": _detect_cycles(relationships),
        },
        "variable_coverage": variables.get("stats") or {},
        "index_consistency": {
            "guideline_count": len(gid_set),
            "index_record_count": len(index_ids),
            "corpus_count": len(corpus_ids),
            "index_aligned": index_ids == gid_set,
            "corpus_aligned": corpus_ids == gid_set,
            "index_missing": sorted(gid_set - index_ids)[:10],
            "index_extra": sorted(index_ids - gid_set)[:10],
        },
        "journey_scope": {
            "journeys": len(journeys),
            "states_per_journey": by_journey_states,
            "state_scoped_buckets": len(state_buckets),
        },
        "rationale": {
            "scope": "Guidelines partitioned into always_on/global/journey/state pools for candidate generation",
            "relationships": "Broker priority edges + heuristic exclusion/dependency/entailment/disambiguation",
            "index": "BM25+vector built from normalized condition_text aligned 1:1 with guideline_id",
        },
    }


def _count_by_type(edges: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in edges:
        t = str(e.get("type") or "unknown")
        out[t] = out.get(t, 0) + 1
    return out
