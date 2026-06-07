from __future__ import annotations

from typing import Any

NO_MATCH_REASONS = (
    "candidate_empty",
    "filtered_empty",
    "not_passed_to_matcher",
    "matcher_rejected_all",
    "telemetry_bug",
    "matched",
)


def build_candidate_entries(trace: Any) -> list[dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    bm25 = set(getattr(trace, "bm25_top_ids", None) or [])
    vector = set(getattr(trace, "vector_top_ids", None) or [])

    for row in getattr(trace, "rrf_candidates", None) or []:
        gid = str(row.get("guideline_id") or "")
        if not gid:
            continue
        sources = []
        if gid in bm25:
            sources.append("bm25")
        if gid in vector:
            sources.append("vector")
        sources.append("rrf")
        entries[gid] = {
            "guideline_id": gid,
            "score": float(row.get("rrf_score") or 0.0),
            "sources": sources,
        }

    for row in getattr(trace, "reranked", None) or []:
        gid = str(row.get("guideline_id") or "")
        if not gid:
            continue
        prev = entries.get(gid, {"guideline_id": gid, "sources": [], "score": 0.0})
        sources = list(prev.get("sources") or [])
        if "rerank" not in sources:
            sources.append("rerank")
        entries[gid] = {
            "guideline_id": gid,
            "score": float(row.get("rerank_score") or row.get("rrf_score") or prev.get("score") or 0.0),
            "sources": sources,
        }

    for gid in getattr(trace, "always_on_injected", None) or []:
        gid = str(gid)
        prev = entries.get(gid, {"guideline_id": gid, "sources": [], "score": 0.0})
        sources = list(prev.get("sources") or [])
        if "always_on" not in sources:
            sources.append("always_on")
        entries[gid] = {**prev, "guideline_id": gid, "sources": sources}

    ordered = list(getattr(trace, "after_relationships", None) or getattr(trace, "candidate_artifact_ids", None) or [])
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for gid in ordered:
        if gid in seen:
            continue
        seen.add(gid)
        out.append(entries.get(gid, {"guideline_id": gid, "score": 0.0, "sources": ["closure"]}))
    for gid, ent in entries.items():
        if gid not in seen:
            out.append(ent)
    return out


def relationship_closure_added_ids(trace: Any) -> list[str]:
    added: list[str] = []
    for item in getattr(trace, "relationship_trace", None) or []:
        action = str(item.get("action") or "")
        if action in {"dependency_add", "entail"}:
            tgt = item.get("target")
            if tgt:
                added.append(str(tgt))
        elif action == "always_on_force":
            tgt = item.get("target")
            if tgt:
                added.append(str(tgt))
    return added


def compute_no_match_reason(
    *,
    candidate_ids: list[str],
    matcher_input_count: int,
    matcher_input_ids: list[str],
    matched_ids: list[str],
    matcher_invocations: int,
) -> str:
    if matched_ids:
        return "matched"
    if matcher_invocations == 0 and matcher_input_count > 0:
        return "telemetry_bug"
    if not candidate_ids:
        return "candidate_empty"
    if matcher_input_count == 0 and candidate_ids:
        return "filtered_empty"
    if matcher_input_count > 0 and matcher_invocations == 0:
        return "not_passed_to_matcher"
    if matcher_input_count > 0 and not matched_ids:
        return "matcher_rejected_all"
    return "telemetry_bug"


def empty_pipeline_link() -> dict[str, Any]:
    return {
        "candidate_guideline_ids": [],
        "always_on_injected_ids": [],
        "relationship_closure_added_ids": [],
        "matcher_input_guideline_ids_count": 0,
        "matcher_input_guideline_ids": [],
        "matched_guideline_ids": [],
        "no_match_reason": "telemetry_bug",
        "matcher_invocations": 0,
    }
