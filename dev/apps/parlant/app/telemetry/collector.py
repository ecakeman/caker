from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from parlant.core.engines.alpha.engine_context import EngineContext
from parlant.core.sessions import EventKind, EventSource

from app.telemetry.judge import judge_response, judge_to_dict
from app.telemetry.pipeline_link import (
    build_candidate_entries,
    compute_no_match_reason,
    empty_pipeline_link,
    relationship_closure_added_ids,
)
from app.telemetry.schema import (
    empty_journey,
    empty_match,
    empty_retrieval,
    empty_timing,
    utc_now_iso,
)
from app.telemetry.content_record import to_content_record, to_debug_record
from app.telemetry.level import is_debug_telemetry
from app.telemetry.writer import append_content_record, append_turn_record


@dataclass
class _StageClock:
    name: str
    start: float = field(default_factory=time.perf_counter)
    ms: float = 0.0

    def stop(self) -> float:
        self.ms = (time.perf_counter() - self.start) * 1000.0
        return self.ms


class TurnCollector:
    def __init__(self, *, root: Any, bundle: Any | None = None) -> None:
        self._root = root
        self._bundle = bundle
        self._started = time.perf_counter()
        self._stage_clocks: dict[str, _StageClock] = {}
        self._timing = empty_timing()
        self._retrieval = empty_retrieval()
        self._match = empty_match()
        self._journey = empty_journey()
        self.session_id = ""
        self.trace_id = ""
        self.turn_index = 0
        self.offset: int | None = None
        self.customer_query = ""
        self.agent_response = ""
        self._pre_journey_id: str | None = None
        self._tool_events_before = 0
        self._llm_calls: list[dict[str, Any]] = []
        self._tool_records: list[dict[str, Any]] = []
        self._matcher_calls = 0
        self._pipeline_link = empty_pipeline_link()
        self._llm_call_seq = 0
        self._current_stage = ""
        self._enforcement_calls_count = 0
        self._enforcement_tokens_total = 0
        self._finalized = False

    def bind_context(self, context: EngineContext) -> None:
        self.session_id = str(context.session.id)
        last_evt = context.interaction.last_customer_message_event
        self.trace_id = (
            (last_evt.trace_id if last_evt else None)
            or context.tracer.trace_id
            or ""
        )
        if last_evt is not None:
            try:
                self.offset = int(last_evt.offset)
            except (TypeError, ValueError, AttributeError):
                self.offset = None
        last_msg = context.interaction.last_customer_message
        self.customer_query = last_msg.content if last_msg else ""
        self.turn_index = sum(
            1
            for e in context.interaction.events
            if e.kind == EventKind.MESSAGE and e.source == EventSource.CUSTOMER
        )
        titles = [str(j.title) for j in context.state.journeys if getattr(j, "title", None)]
        self._journey["journey_titles"] = titles
        if self._bundle is not None:
            title_map = {
                str(j.get("title") or ""): str(j.get("journey_id") or "")
                for j in self._bundle.journeys
            }
            for title in titles:
                jid = title_map.get(title)
                if jid:
                    self._pre_journey_id = jid
                    self._journey["active_journey_id"] = jid
                    break
        self._tool_events_before = len(context.state.tool_events)

    def start_stage(self, name: str) -> None:
        self._current_stage = name
        self._stage_clocks[name] = _StageClock(name=name)

    def stop_stage(self, name: str) -> float:
        clock = self._stage_clocks.get(name)
        if clock is None:
            return 0.0
        ms = clock.stop()
        self._timing["stages_ms"][name] = round(ms, 2)
        if self._current_stage == name:
            self._current_stage = ""
        return ms

    def record_retrieval_pass(self, trace: Any, *, retrieval_ms: float) -> None:
        if self._matcher_calls == 0:
            self.stop_stage("retrieval")
        self._timing["stages_ms"]["retrieval"] = round(
            float(self._timing["stages_ms"].get("retrieval", 0.0)) + retrieval_ms,
            2,
        )
        self._retrieval["query_original"] = trace.query_original
        self._retrieval["query_rewritten"] = trace.query_rewritten
        self._retrieval["enforcement_level"] = getattr(trace, "enforcement_level", "medium")
        sf = trace.scope_filter or {}
        self._retrieval["scope_pool_size"] = sf.get("pool_size")
        self._retrieval["adaptive_k"] = trace.adaptive_k
        closed = list(trace.after_relationships or [])
        rel_trace = list(trace.relationship_trace or [])
        rel_added = sum(
            1 for t in rel_trace if str(t.get("action") or "") in {"dependency_add", "entail", "always_on_force"}
        )
        always_on = list(trace.always_on_injected or [])
        if getattr(trace, "enforcement_level", "medium") == "low":
            required = list(always_on)
        else:
            required = list((self._bundle.scope_map.get("always_on") or []) if self._bundle else [])
        present = set(closed)
        always_present = [gid for gid in required if gid in present]
        always_missing = [gid for gid in required if gid not in present]
        self._retrieval["counts"] = {
            "scope_pool": int(sf.get("pool_size") or 0),
            "bm25": len(trace.bm25_top_ids or []),
            "vector": len(trace.vector_top_ids or []),
            "rrf": len(trace.rrf_candidates or []),
            "reranked": len(trace.reranked or []),
            "relationship_added": rel_added,
            "always_on_injected": len(always_on),
            "matcher_input": trace.input_guideline_count,
            "matcher_output": trace.output_guideline_count,
        }
        topk: list[dict[str, Any]] = []
        for i, row in enumerate(trace.reranked or []):
            topk.append(
                {
                    "guideline_id": row.get("guideline_id"),
                    "source": "rerank",
                    "score": float(row.get("rerank_score") or row.get("rrf_score") or 0.0),
                    "rank": i + 1,
                }
            )
        for i, row in enumerate(trace.rrf_candidates or []):
            gid = row.get("guideline_id")
            if any(t.get("guideline_id") == gid for t in topk):
                continue
            topk.append(
                {
                    "guideline_id": gid,
                    "source": "rrf",
                    "score": float(row.get("rrf_score") or 0.0),
                    "rank": len(topk) + 1,
                }
            )
        self._retrieval["topk"] = topk[:20]
        self._retrieval["always_on_required"] = required
        self._retrieval["always_on_present"] = always_present
        self._retrieval["always_on_ok"] = len(always_present) == len(required) if required else True
        self._retrieval["always_on_missing"] = always_missing
        self._retrieval["relationship_trace"] = rel_trace

        candidates = build_candidate_entries(trace)
        merged: dict[str, dict[str, Any]] = {
            c["guideline_id"]: c for c in (self._pipeline_link.get("candidate_guideline_ids") or [])
        }
        for c in candidates:
            merged[c["guideline_id"]] = c
        self._pipeline_link["candidate_guideline_ids"] = list(merged.values())
        always = set(self._pipeline_link.get("always_on_injected_ids") or [])
        always.update(trace.always_on_injected or [])
        self._pipeline_link["always_on_injected_ids"] = sorted(always)
        rel_added = set(self._pipeline_link.get("relationship_closure_added_ids") or [])
        rel_added.update(relationship_closure_added_ids(trace))
        self._pipeline_link["relationship_closure_added_ids"] = sorted(rel_added)

    def record_match_pass(
        self,
        *,
        trace: Any,
        matcher_ids: list[str],
        batch_count: int | None,
        judge_match_ms: float,
        filtered_count: int,
    ) -> None:
        self._matcher_calls += 1
        self._pipeline_link["matcher_invocations"] = self._matcher_calls
        self._timing["stages_ms"]["judge_match"] = round(
            float(self._timing["stages_ms"].get("judge_match", 0.0)) + judge_match_ms,
            2,
        )

        input_ids = list(trace.matcher_input_artifact_ids or [])
        prev_inputs = set(self._pipeline_link.get("matcher_input_guideline_ids") or [])
        for gid in input_ids:
            prev_inputs.add(gid)
        self._pipeline_link["matcher_input_guideline_ids"] = sorted(prev_inputs)
        self._pipeline_link["matcher_input_guideline_ids_count"] = len(prev_inputs)

        existing = set(self._pipeline_link.get("matched_guideline_ids") or [])
        for gid in matcher_ids:
            existing.add(gid)
        matched_sorted = sorted(existing)
        self._pipeline_link["matched_guideline_ids"] = matched_sorted

        self._match["matched_guideline_ids"] = matched_sorted
        self._match["matcher_batches"] = int(batch_count or 0) + int(self._match.get("matcher_batches") or 0)
        self._match["matcher_match_count"] = len(matched_sorted)

        candidate_ids = [c["guideline_id"] for c in self._pipeline_link.get("candidate_guideline_ids") or []]
        topk_set = set(candidate_ids)
        self._match["false_positive_ids"] = sorted(gid for gid in matched_sorted if gid not in topk_set)

        if filtered_count == 0 and not input_ids and candidate_ids:
            self._pipeline_link["no_match_reason"] = "filtered_empty"
        elif filtered_count > 0 and self._matcher_calls >= 1:
            pass  # defer until finalize

        journey_pool: list[str] = []
        jid = self._journey.get("active_journey_id")
        if self._bundle and jid:
            journey_pool = list(self._bundle.scope_map.get("journey_scoped", {}).get(jid, []))
        self._match["journey_pool_ids"] = journey_pool
        if journey_pool:
            pool_set = set(journey_pool)
            matched_in_pool = [gid for gid in matched_sorted if gid in pool_set]
            self._match["recall_at_k"] = round(len(matched_in_pool) / max(len(pool_set), 1), 4)
            self._match["false_negative_ids"] = sorted(
                gid for gid in pool_set if gid not in matched_sorted and gid in topk_set
            )
        else:
            self._match["recall_at_k"] = None
            self._match["false_negative_ids"] = []

    def record_llm_call(
        self,
        *,
        stage: str,
        schema_name: str,
        model: str,
        latency_ms: float,
        prompt_tokens: int,
        completion_tokens: int,
        retries: int = 0,
        error: str | None = None,
    ) -> None:
        self._llm_call_seq += 1
        rec = {
            "call_index": self._llm_call_seq,
            "stage": stage,
            "schema_name": schema_name,
            "model": model,
            "latency_ms": round(latency_ms, 2),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "retries": retries,
            "error": error,
        }
        self._llm_calls.append(rec)
        if self._current_stage == "arq_enforcement" or stage not in {"compose"}:
            self._enforcement_calls_count += 1
            self._enforcement_tokens_total += rec["total_tokens"]
        llm = self._timing["llm"]
        llm["calls"] = len(self._llm_calls)
        llm["prompt_tokens_sum"] = sum(c["prompt_tokens"] for c in self._llm_calls)
        llm["completion_tokens_sum"] = sum(c["completion_tokens"] for c in self._llm_calls)
        llm["total_tokens_sum"] = sum(c["total_tokens"] for c in self._llm_calls)
        llm["prompt_tokens_avg"] = round(llm["prompt_tokens_sum"] / max(len(self._llm_calls), 1), 1)
        llm["total_tokens_avg"] = round(llm["total_tokens_sum"] / max(len(self._llm_calls), 1), 1)
        llm["latency_ms_total"] = round(sum(c["latency_ms"] for c in self._llm_calls), 2)
        llm["retries"] += retries
        llm["calls_detail"] = self._llm_calls

    def note_executed_tools(self, tool_ids: list[Any]) -> None:
        names = []
        for tid in tool_ids:
            raw = str(getattr(tid, "tool_name", None) or tid)
            names.append(raw.split(":", 1)[1] if ":" in raw else raw)
        self._match.setdefault("executed_tools", [])
        for name in names:
            if name not in self._match["executed_tools"]:
                self._match["executed_tools"].append(name)

    def note_material_fast_path(self, tool_names: list[str]) -> None:
        self._timing.setdefault("material_fast_path", {})
        self._timing["material_fast_path"] = {
            "applied": True,
            "executed_tools": tool_names,
            "decision": "prepared_without_rematch",
        }

    def _tool_id_short(self, raw: str) -> str:
        return raw.split(":", 1)[1] if ":" in raw else raw

    def sync_tools_from_context(self, context: EngineContext) -> None:
        new_events = context.state.tool_events[self._tool_events_before :]
        tools = self._timing["tools"]
        seen = {r.get("tool_call_id") or r.get("tool_id") for r in self._tool_records}
        for ev in new_events:
            data = ev.data if isinstance(ev.data, dict) else {}
            tool_calls = data.get("tool_calls") if isinstance(data.get("tool_calls"), list) else []
            if tool_calls:
                for call in tool_calls:
                    if not isinstance(call, dict):
                        continue
                    tool_id = self._tool_id_short(str(call.get("tool_id") or "unknown"))
                    tool_call_id = str(
                        call.get("tool_call_id")
                        or call.get("id")
                        or call.get("call_id")
                        or f"{tool_id}:{len(self._tool_records) + 1}"
                    )
                    if tool_call_id in seen:
                        continue
                    seen.add(tool_call_id)
                    result = call.get("result") if isinstance(call.get("result"), dict) else {}
                    payload = result.get("data") if isinstance(result.get("data"), dict) else {}
                    ok = payload.get("ok", True) if isinstance(payload, dict) else True
                    lookup_mode = payload.get("lookup_mode") or payload.get("lookup", {})
                    if isinstance(lookup_mode, dict) and str(lookup_mode.get("mode", "")).startswith("miss"):
                        ok = False
                    if isinstance(lookup_mode, str) and lookup_mode in {"need_params", "need_topic_clarification"}:
                        ok = False
                    arguments = dict(call.get("arguments") or {}) if isinstance(call.get("arguments"), dict) else {}
                    error_type = None if ok else str(payload.get("reason") or "")
                    if not error_type and isinstance(lookup_mode, str):
                        error_type = lookup_mode
                    if not error_type and isinstance(lookup_mode, dict):
                        error_type = str(lookup_mode.get("mode") or "")
                    rec = {
                        "tool_id": tool_id,
                        "tool_call_id": tool_call_id,
                        "latency_ms": 0.0,
                        "success": bool(ok),
                        "retries": 0,
                        "error": None if ok else str(payload.get("reason") or lookup_mode),
                        "error_type": error_type or None,
                        "error_msg": None if ok else str(payload.get("message") or payload.get("reason") or lookup_mode),
                        "input_summary": {
                            "topic": str(arguments.get("topic") or "")[:120],
                            "reuse_id": arguments.get("reuse_id"),
                            "material_slot_id": arguments.get("material_slot_id"),
                        },
                        "status_code": payload.get("status_code"),
                        "output_url": payload.get("output_url"),
                        "attachment_id": payload.get("attachment_id"),
                        "fallback_no_image": bool(payload.get("fallback_no_image")),
                        "arguments": arguments,
                    }
                    self._tool_records.append(rec)
                    tools["calls"] += 1
                    if not ok:
                        tools["failures"] += 1
            else:
                tool_id = self._tool_id_short(str(data.get("tool_id") or data.get("name") or "unknown"))
                if tool_id in seen:
                    continue
                seen.add(tool_id)
                latency = float(data.get("duration_ms") or data.get("latency_ms") or 0.0)
                ok = not bool(data.get("error") or data.get("failed"))
                rec = {
                    "tool_id": tool_id,
                    "latency_ms": round(latency, 2),
                    "success": ok,
                    "retries": int(data.get("retries") or 0),
                    "error": str(data.get("error") or "") or None,
                    "error_type": str(data.get("error_type") or "") or None,
                    "error_msg": str(data.get("error") or data.get("message") or "") or None,
                    "input_summary": {},
                    "status_code": data.get("status_code"),
                }
                self._tool_records.append(rec)
                tools["calls"] += 1
                tools["latency_ms_total"] = round(float(tools["latency_ms_total"]) + latency, 2)
                if not ok:
                    tools["failures"] += 1
                tools["retries"] += int(data.get("retries") or 0)
        tools["records"] = self._tool_records
        self._timing["stages_ms"]["tools"] = round(
            sum(float(r.get("latency_ms") or 0) for r in self._tool_records),
            2,
        )

    def rendered_material_tokens(self) -> list[str]:
        tokens: list[str] = []
        seen: set[str] = set()
        for rec in self._tool_records:
            if not rec.get("success", True):
                continue
            tool_id = str(rec.get("tool_id") or "")
            summary = rec.get("input_summary") or {}
            reuse_id = str(summary.get("reuse_id") or "").strip()
            if not reuse_id:
                attachment = str(rec.get("attachment_id") or "")
                if ":" in attachment:
                    reuse_id = attachment.split(":", 1)[1].strip()
            if not reuse_id:
                continue
            prefix = {
                "send_image": "图片",
                "send_link": "链接",
                "send_quoted_chat": "引用",
            }.get(tool_id)
            if not prefix:
                continue
            token = f"[{prefix}:{reuse_id}]"
            if token not in seen:
                tokens.append(token)
                seen.add(token)
        return tokens

    def set_agent_response(self, text: str) -> None:
        self.agent_response = (text or "").strip()

    def _refresh_journey_match_metrics(self, context: EngineContext) -> None:
        post_jid = self._journey.get("active_journey_id")
        titles = [str(j.title) for j in context.state.journeys if getattr(j, "title", None)]
        self._journey["journey_titles"] = titles
        if self._bundle and context.state.journeys:
            title_map = {
                str(j.get("title") or ""): str(j.get("journey_id") or "")
                for j in self._bundle.journeys
            }
            for j in context.state.journeys:
                post_jid = title_map.get(str(j.title)) or post_jid
        self._journey["post_journey_id"] = post_jid
        self._journey["active_journey_id"] = post_jid
        self._journey["transitioned"] = post_jid != self._pre_journey_id
        matched = list(self._match.get("matched_guideline_ids") or [])
        topk_ids = [str(r.get("guideline_id")) for r in self._retrieval.get("topk") or [] if r.get("guideline_id")]
        journey_pool: list[str] = []
        if self._bundle and post_jid:
            journey_pool = list(self._bundle.scope_map.get("journey_scoped", {}).get(post_jid, []))
        self._match["journey_pool_ids"] = journey_pool
        if journey_pool:
            pool_set = set(journey_pool)
            matched_in_pool = [gid for gid in matched if gid in pool_set]
            self._match["recall_at_k"] = round(len(matched_in_pool) / max(len(pool_set), 1), 4)
            self._match["false_negative_ids"] = sorted(
                gid for gid in pool_set if gid not in matched and gid in topk_ids
            )
        self._journey["stuck"] = (
            bool(post_jid)
            and not matched
            and self._matcher_calls > 0
        )

    def finalize(self, context: EngineContext | None = None) -> dict[str, Any] | None:
        if self._finalized:
            return None
        self._finalized = True
        if context is not None:
            self.sync_tools_from_context(context)
            self._refresh_journey_match_metrics(context)
            if not self.agent_response and context.state.message_events:
                parts = []
                for ev in context.state.message_events:
                    if isinstance(ev.data, dict):
                        parts.append(str(ev.data.get("message") or ""))
                self.agent_response = "\n".join(p for p in parts if p).strip()

        self._timing["e2e_ms"] = round((time.perf_counter() - self._started) * 1000.0, 2)
        self._timing["enforcement"] = {
            "calls_count": self._enforcement_calls_count,
            "tokens_total": self._enforcement_tokens_total,
        }
        stages = self._timing["stages_ms"]
        if stages:
            slowest = max(stages.items(), key=lambda kv: kv[1])
            self._timing["slowest_stage"] = slowest[0] if slowest[1] > 0 else ""

        self._journey["pre_journey_id"] = self._pre_journey_id

        pl = self._pipeline_link
        candidate_ids = [c["guideline_id"] for c in pl.get("candidate_guideline_ids") or []]
        pl["no_match_reason"] = compute_no_match_reason(
            candidate_ids=candidate_ids,
            matcher_input_count=int(pl.get("matcher_input_guideline_ids_count") or 0),
            matcher_input_ids=list(pl.get("matcher_input_guideline_ids") or []),
            matched_ids=list(pl.get("matched_guideline_ids") or []),
            matcher_invocations=int(pl.get("matcher_invocations") or 0),
        )

        topk_ids = candidate_ids or [
            str(r.get("guideline_id")) for r in self._retrieval.get("topk") or [] if r.get("guideline_id")
        ]
        judge = judge_response(
            customer_query=self.customer_query,
            agent_response=self.agent_response,
            matched_guideline_ids=list(self._match.get("matched_guideline_ids") or []),
            retrieval_topk_ids=topk_ids,
            active_journey_id=self._journey.get("active_journey_id"),
            always_on_ok=bool(self._retrieval.get("always_on_ok", True)),
        )

        session_event_count = None
        if context is not None:
            session_event_count = len(context.interaction.events)

        record = {
            "v": "2",
            "ts": utc_now_iso(),
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "turn_index": self.turn_index,
            "offset": self.offset,
            "customer_query": self.customer_query[:2000],
            "agent_response": self.agent_response[:4000],
            "timing": self._timing,
            "retrieval": self._retrieval,
            "match": self._match,
            "journey": self._journey,
            "response_judge": judge_to_dict(judge),
            "candidate_guideline_ids": pl.get("candidate_guideline_ids") or [],
            "always_on_injected_ids": pl.get("always_on_injected_ids") or [],
            "relationship_closure_added_ids": pl.get("relationship_closure_added_ids") or [],
            "matcher_input_guideline_ids_count": int(pl.get("matcher_input_guideline_ids_count") or 0),
            "matched_guideline_ids": pl.get("matched_guideline_ids") or [],
            "no_match_reason": pl.get("no_match_reason") or "telemetry_bug",
            "pipeline_link": pl,
        }
        compact = to_content_record(record, session_event_count=session_event_count)
        append_content_record(compact, root=self._root)
        if is_debug_telemetry():
            append_turn_record(to_debug_record(record), root=self._root)
        return record
