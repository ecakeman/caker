from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.artifacts import ArtifactBundle
from app.matching.judge import judge_candidates
from app.matching.query import QueryBundle, build_query, maybe_rewrite_query
from app.matching.relationships import apply_relationship_closure
from app.matching.rerank import rerank_candidates
from app.matching.retrieval import GuidelineIndex
from app.matching.trace_log import append_match_trace


@dataclass
class MatchTrace:
    query: str
    query_bundle: dict[str, Any] = field(default_factory=dict)
    scope_filter: dict[str, Any] = field(default_factory=dict)
    retrieval_meta: dict[str, Any] = field(default_factory=dict)
    retrieval: list[dict[str, Any]] = field(default_factory=list)
    reranked: list[dict[str, Any]] = field(default_factory=list)
    after_relationships: list[str] = field(default_factory=list)
    relationship_trace: list[dict[str, Any]] = field(default_factory=list)
    final_matches: list[dict[str, Any]] = field(default_factory=list)
    always_on_injected: list[str] = field(default_factory=list)
    adaptive_k: int = 5


class GuidelineMatchingEngine:
    def __init__(self, bundle: ArtifactBundle, settings: Any) -> None:
        self.bundle = bundle
        self.settings = settings
        self.index = GuidelineIndex(bundle.root, bundle.index_meta)

    def _scope_pool(self, active_journey_id: str | None, active_state_id: str | None) -> set[str] | None:
        sm = self.bundle.scope_map
        if not active_journey_id:
            return None
        pool = set(sm.get("journey_scoped", {}).get(active_journey_id, []))
        if active_state_id:
            pool.update(sm.get("state_scoped", {}).get(f"{active_journey_id}::{active_state_id}", []))
        pool.update(sm.get("global", []))
        return pool

    def _adaptive_top_k(self, retrieved: list[dict[str, Any]], query: str) -> int:
        base = self.settings.matching_top_k
        if any(k in query for k in ("合规", "返佣", "监管", "健康告知", "拒保")):
            return max(base, 8)
        if not retrieved:
            return base
        top_rrf = float(retrieved[0].get("rrf_score") or 0.0)
        if top_rrf < 0.02:
            return max(base, 8)
        return base

    def match(
        self,
        user_message: str,
        *,
        session_summary: str = "",
        active_journey_id: str | None = None,
        active_state_id: str | None = None,
        use_llm_judge: bool = True,
        use_query_rewrite: bool | None = None,
        write_trace: bool = False,
        trace_path: Path | None = None,
    ) -> MatchTrace:
        base_query = build_query(
            user_message,
            session_summary=session_summary,
            active_journey_id=active_journey_id,
            active_state_id=active_state_id,
        )
        rewrite_enabled = (
            use_query_rewrite
            if use_query_rewrite is not None
            else (os.environ.get("MATCHING_QUERY_REWRITE", "0").strip() == "1")
        )
        qb: QueryBundle = maybe_rewrite_query(
            base_query,
            llm_model=self.settings.llm_model,
            llm_base_url=self.settings.llm_base_url,
            llm_api_key=self.settings.llm_api_key,
            enabled=rewrite_enabled,
        )
        trace = MatchTrace(
            query=base_query,
            query_bundle={"original": qb.original, "rewritten": qb.rewritten},
            scope_filter={
                "active_journey_id": active_journey_id,
                "active_state_id": active_state_id,
            },
        )
        extra = [qb.rewritten] if qb.rewritten else None
        retrieved, retrieval_meta = self.index.search(
            qb.original,
            top_k=self.settings.matching_top_k,
            rrf_k=self.settings.matching_rrf_k,
            embedding_model=self.settings.embedding_model,
            embedding_base_url=self.settings.embedding_base_url,
            embedding_api_key=self.settings.embedding_api_key,
            embedding_dimensions=self.settings.embedding_dimensions,
            extra_queries=extra,
        )
        trace.retrieval_meta = retrieval_meta
        pool = self._scope_pool(active_journey_id, active_state_id)
        if pool is not None:
            retrieved = [r for r in retrieved if r["guideline_id"] in pool]
        top_k = self._adaptive_top_k(retrieved, base_query)
        trace.adaptive_k = top_k
        reranked = rerank_candidates(
            qb.original,
            retrieved[:top_k],
            embedding_model=self.settings.embedding_model,
            embedding_base_url=self.settings.embedding_base_url,
            embedding_api_key=self.settings.embedding_api_key,
            embedding_dimensions=self.settings.embedding_dimensions,
            record_vectors=self.index.vectors,
            id_to_idx=self.index.id_to_idx,
        )
        trace.reranked = reranked
        always_on = set(self.bundle.scope_map.get("always_on") or [])
        retrieved_ids = {r["guideline_id"] for r in reranked}
        merged = list(reranked)
        for gid in always_on:
            if gid not in retrieved_ids:
                rec = next((x for x in self.bundle.index_records if x["guideline_id"] == gid), None)
                if rec:
                    merged.append({**rec, "rrf_score": 0.0, "always_on": True})
                    trace.always_on_injected.append(gid)
        trace.retrieval = merged
        candidate_ids = [r["guideline_id"] for r in merged]
        closed, rel_trace = apply_relationship_closure(candidate_ids, self.bundle.relationships)
        trace.after_relationships = closed
        trace.relationship_trace = rel_trace
        closed_records = [r for r in merged if r["guideline_id"] in closed]
        if use_llm_judge:
            trace.final_matches = judge_candidates(
                base_query,
                closed_records,
                llm_model=self.settings.llm_model,
                llm_base_url=self.settings.llm_base_url,
                llm_api_key=self.settings.llm_api_key,
            )
        else:
            trace.final_matches = closed_records
        if write_trace and trace_path:
            append_match_trace(trace, trace_path)
        return trace
