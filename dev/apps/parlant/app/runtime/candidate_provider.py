from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Sequence

from parlant.core.engines.alpha.engine_context import EngineContext
from parlant.core.guidelines import Guideline
from parlant.core.journeys import Journey

from app.artifacts import ArtifactBundle
from app.config import AppSettings
from app.governance.matcher_context import build_matcher_evidence_projection
from app.matching.query import QueryBundle, build_query, maybe_rewrite_query
from app.matching.relationships import apply_relationship_closure
from app.matching.rerank import rerank_candidates
from app.matching.retrieval import GuidelineIndex
from app.runtime.guideline_registry import GuidelineRegistry


@dataclass
class CandidateTrace:
    trace_id: str = ""
    session_id: str = ""
    query_original: str = ""
    query_rewritten: str | None = None
    active_journey_id: str | None = None
    active_state_id: str | None = None
    scope_filter: dict[str, Any] = field(default_factory=dict)
    retrieval_meta: dict[str, Any] = field(default_factory=dict)
    bm25_top_ids: list[str] = field(default_factory=list)
    vector_top_ids: list[str] = field(default_factory=list)
    rrf_candidates: list[dict[str, Any]] = field(default_factory=list)
    reranked: list[dict[str, Any]] = field(default_factory=list)
    adaptive_k: int = 5
    enforcement_level: str = "medium"
    always_on_injected: list[str] = field(default_factory=list)
    after_relationships: list[str] = field(default_factory=list)
    relationship_trace: list[dict[str, Any]] = field(default_factory=list)
    candidate_artifact_ids: list[str] = field(default_factory=list)
    matcher_input_artifact_ids: list[str] = field(default_factory=list)
    pre_scope_retrieval_count: int = 0
    scope_emptied: bool = False
    input_guideline_count: int = 0
    output_guideline_count: int = 0
    unmapped_guideline_count: int = 0


class CandidateGuidelineProvider:
    """Two-stage retrieval candidate generator (no LLM judge — native matcher decides)."""

    def __init__(self, bundle: ArtifactBundle, settings: AppSettings) -> None:
        self.bundle = bundle
        self.settings = settings
        self.index = GuidelineIndex(bundle.root, bundle.index_meta)
        self.registry = GuidelineRegistry(bundle.guidelines)
        self._title_to_journey_id = {
            str(j.get("title") or ""): str(j.get("journey_id") or "")
            for j in bundle.journeys
        }

    def _is_high_risk_query(self, query: str) -> bool:
        return any(k in query for k in ("合规", "返佣", "健康告知", "拒保", "投诉", "隐私", "一定赔", "保证赔"))

    def _low_risk_always_on(self) -> set[str]:
        always_on = set(self.bundle.scope_map.get("always_on") or [])
        by_id = {str(g.get("guideline_id")): g for g in self.bundle.guidelines}
        return {
            gid
            for gid in always_on
            if by_id.get(gid) and (by_id[gid].get("tools") or by_id[gid].get("tool_actions"))
        }

    def _scope_pool(
        self,
        active_journey_id: str | None,
        active_state_id: str | None,
    ) -> set[str] | None:
        sm = self.bundle.scope_map
        if not active_journey_id:
            return None
        pool = set(sm.get("journey_scoped", {}).get(active_journey_id, []))
        if active_state_id:
            pool.update(sm.get("state_scoped", {}).get(f"{active_journey_id}::{active_state_id}", []))
        pool.update(sm.get("global", []))
        pool.update(sm.get("always_on") or [])
        return pool

    def _adaptive_top_k(self, retrieved: list[dict[str, Any]], query: str) -> int:
        base = self.settings.matching_top_k
        max_k = int((os.environ.get("MATCHING_ADAPTIVE_K_MAX") or "12").strip())
        high_risk = self._is_high_risk_query(query)
        if high_risk:
            return max(base, max_k)
        return base

    def _context_query(self, context: EngineContext) -> tuple[str, str, str | None, str | None]:
        last = context.interaction.last_customer_message
        user_message = last.content if last else ""
        trace_id = (last.trace_id if last else None) or context.tracer.trace_id
        parts: list[str] = []
        for msg in context.interaction.messages[-6:]:
            parts.append(f"{msg.source}: {msg.content}")
        session_summary = "\n".join(parts[:-1]) if len(parts) > 1 else ""
        active_journey_id: str | None = None
        if context.state.journeys:
            titles = [str(j.title) for j in context.state.journeys if getattr(j, "title", None)]
            for title in titles:
                jid = self._title_to_journey_id.get(title)
                if jid:
                    active_journey_id = jid
                    break
            if not active_journey_id and context.state.journeys:
                active_journey_id = self._title_to_journey_id.get(str(context.state.journeys[0].title))
        active_state_id = None
        return user_message, trace_id, active_journey_id, active_state_id

    def generate(
        self,
        context: EngineContext,
        *,
        active_journeys: Sequence[Journey],
        guidelines: Sequence[Guideline],
    ) -> tuple[list[Guideline], CandidateTrace]:
        user_message, trace_id, active_journey_id, active_state_id = self._context_query(context)
        if not active_journey_id and active_journeys:
            active_journey_id = self._title_to_journey_id.get(str(active_journeys[0].title))

        recent: list[str] = []
        for msg in context.interaction.messages[-4:]:
            recent.append(f"{msg.source}: {msg.content[:100]}")
        evidence = build_matcher_evidence_projection(
            user_message=user_message,
            active_journey_id=active_journey_id,
            active_state_id=active_state_id,
            recent_messages=recent,
            state_markers=[f"state_active_journey={active_journey_id}"] if active_journey_id else None,
        )
        base_query = build_query(
            evidence,
            session_summary="",
            active_journey_id=active_journey_id,
            active_state_id=active_state_id,
        )
        rewrite_enabled = (os.environ.get("MATCHING_QUERY_REWRITE", "0").strip() == "1")
        qb: QueryBundle = maybe_rewrite_query(
            base_query,
            llm_model=self.settings.llm_model,
            llm_base_url=self.settings.llm_base_url,
            llm_api_key=self.settings.llm_api_key,
            enabled=rewrite_enabled,
        )
        trace = CandidateTrace(
            trace_id=trace_id,
            session_id=str(context.session.id),
            query_original=base_query,
            query_rewritten=qb.rewritten,
            active_journey_id=active_journey_id,
            active_state_id=active_state_id,
            input_guideline_count=len(guidelines),
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
        trace.bm25_top_ids = list(retrieval_meta.get("bm25_top_ids") or [])
        trace.vector_top_ids = list(retrieval_meta.get("vector_top_ids") or [])
        trace.rrf_candidates = [
            {"guideline_id": r["guideline_id"], "rrf_score": r.get("rrf_score"), "bm25_score": r.get("bm25_score"), "vector_score": r.get("vector_score")}
            for r in retrieved
        ]

        pool = self._scope_pool(active_journey_id, active_state_id)
        trace.scope_filter = {
            "active_journey_id": active_journey_id,
            "active_state_id": active_state_id,
            "pool_size": len(pool) if pool is not None else None,
            "applied": pool is not None,
        }
        high_risk = self._is_high_risk_query(base_query)
        trace.enforcement_level = "high" if high_risk else "low"
        always_on = set(self.bundle.scope_map.get("always_on") or []) if high_risk else self._low_risk_always_on()
        trace.pre_scope_retrieval_count = len(retrieved)
        if pool is not None:
            scoped = [r for r in retrieved if r["guideline_id"] in pool]
            if not scoped and retrieved:
                trace.scope_emptied = True
                relaxed = set(self.bundle.scope_map.get("global") or []) | always_on
                if active_journey_id:
                    relaxed.update(self.bundle.scope_map.get("journey_scoped", {}).get(active_journey_id, []))
                scoped = [r for r in retrieved if r["guideline_id"] in relaxed]
                if not scoped:
                    scoped = retrieved[: max(self.settings.matching_top_k, 8)]
                trace.scope_filter["relaxed"] = True
            retrieved = scoped

        top_k = self._adaptive_top_k(retrieved, base_query)
        if high_risk:
            top_k = max(top_k, int((os.environ.get("MATCHING_ADAPTIVE_K_MAX") or "12").strip()))
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
        trace.reranked = [
            {"guideline_id": r["guideline_id"], "rrf_score": r.get("rrf_score"), "rerank_score": r.get("rerank_score")}
            for r in reranked
        ]

        merged_ids = {r["guideline_id"] for r in reranked}
        merged_records = list(reranked)
        if trace.scope_emptied and active_journey_id:
            for gid in list(self.bundle.scope_map.get("journey_scoped", {}).get(active_journey_id, []))[:10]:
                if gid in merged_ids:
                    continue
                rec = next((x for x in self.bundle.index_records if x["guideline_id"] == gid), None)
                if rec:
                    merged_records.append({**rec, "rrf_score": 0.0, "journey_boost": True})
                    merged_ids.add(gid)
        for gid in always_on:
            if gid not in merged_ids:
                rec = next((x for x in self.bundle.index_records if x["guideline_id"] == gid), None)
                if rec:
                    merged_records.append({**rec, "rrf_score": 0.0, "always_on": True})
                    trace.always_on_injected.append(gid)
                    merged_ids.add(gid)

        candidate_ids = [r["guideline_id"] for r in merged_records]
        closed, rel_trace = apply_relationship_closure(candidate_ids, self.bundle.relationships)
        closed_set = set(closed)
        for gid in always_on:
            if gid not in closed_set:
                closed.append(gid)
                closed_set.add(gid)
                rel_trace.append({"action": "always_on_force", "target": gid})
        trace.after_relationships = closed
        trace.relationship_trace = rel_trace
        trace.candidate_artifact_ids = closed
        allowed = closed_set

        filtered: list[Guideline] = []
        unmapped = 0
        for g in guidelines:
            aid = self.registry.artifact_id(g)
            if aid is None:
                unmapped += 1
                filtered.append(g)
                continue
            if aid in allowed:
                filtered.append(g)

        trace.matcher_input_artifact_ids = sorted(
            {aid for aid in (self.registry.artifact_id(g) for g in filtered) if aid}
        )
        trace.output_guideline_count = len(filtered)
        trace.unmapped_guideline_count = unmapped
        return filtered, trace
