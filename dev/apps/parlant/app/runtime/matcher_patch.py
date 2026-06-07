from __future__ import annotations

import logging
import os
import time
from functools import wraps
from typing import Any, Callable

from parlant.core.engines.alpha.guideline_matching.guideline_match import GuidelineMatch
from parlant.core.engines.alpha.guideline_matching.guideline_matcher import (
    GuidelineMatcher,
    GuidelineMatchingResult,
)

from app.artifacts import load_artifacts
from app.config import AppSettings
from app.runtime.candidate_provider import CandidateGuidelineProvider
from app.telemetry.context import get_collector

_logger = logging.getLogger(__name__)
_PATCH_APPLIED = False
_ORIGINAL_MATCH: Callable[..., Any] | None = None
_PROVIDER: CandidateGuidelineProvider | None = None


def _enabled() -> bool:
    return (os.environ.get("PARLANT_CANDIDATE_PROVIDER") or "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _matcher_artifact_ids(provider: CandidateGuidelineProvider, result: Any) -> list[str]:
    ids: list[str] = []
    for match in getattr(result, "matches", []) or []:
        gid = provider.registry.artifact_id(match.guideline)
        if gid:
            ids.append(gid)
    return ids


def _token_overlap(a: str, b: str) -> int:
    keys = {
        "图",
        "截图",
        "链接",
        "理赔",
        "倒闭",
        "小公司",
        "线上",
        "监管",
        "网点",
        "保单",
        "合同",
        "健康告知",
        "拒赔",
        "投保",
    }
    return sum(1 for k in keys if k in a and k in b)


def _guideline_text(guideline: Any) -> str:
    content = getattr(guideline, "content", None)
    return f"{getattr(content, 'condition', '')} {getattr(content, 'action', '')}"


def _fast_match_result(
    provider: CandidateGuidelineProvider,
    filtered: list[Any],
    trace: Any,
) -> GuidelineMatchingResult:
    query = str(getattr(trace, "query_original", "") or "")
    reranked_ids = [str(r.get("guideline_id")) for r in (getattr(trace, "reranked", []) or [])[:3]]
    artifact_meta = {str(g.get("guideline_id")): g for g in provider.bundle.guidelines}
    selected: list[Any] = []
    seen: set[str] = set()
    for guideline in filtered:
        aid = provider.registry.artifact_id(guideline)
        if not aid or aid in seen:
            continue
        text = _guideline_text(guideline)
        meta = artifact_meta.get(aid) or {}
        has_tools = bool(meta.get("tools") or meta.get("tool_actions"))
        if aid in reranked_ids or (has_tools and _token_overlap(query, text) > 0):
            selected.append(guideline)
            seen.add(aid)
        if len(selected) >= 2:
            break

    matches = [
        GuidelineMatch(
            guideline=g,
            score=10,
            rationale="deterministic low-risk candidate fast-path",
            metadata={"fast_path": True},
        )
        for g in selected
    ]
    return GuidelineMatchingResult(
        total_duration=0.0,
        batch_count=0,
        batch_generations=[],
        batches=[matches],
        matches=matches,
    )


def apply_candidate_provider_patch(settings: AppSettings) -> None:
    global _PATCH_APPLIED, _ORIGINAL_MATCH, _PROVIDER
    if _PATCH_APPLIED or not _enabled():
        if not _enabled():
            _logger.info("candidate_provider: disabled (PARLANT_CANDIDATE_PROVIDER=0)")
        return

    bundle = load_artifacts(settings.artifacts_root)
    _PROVIDER = CandidateGuidelineProvider(bundle, settings)
    _ORIGINAL_MATCH = GuidelineMatcher.match_guidelines

    @wraps(_ORIGINAL_MATCH)
    async def patched_match_guidelines(
        self: GuidelineMatcher,
        context: Any,
        active_journeys: Any,
        guidelines: Any,
    ) -> Any:
        assert _PROVIDER is not None
        assert _ORIGINAL_MATCH is not None
        collector = get_collector()
        if collector is not None and collector._matcher_calls == 0:
            collector.start_stage("retrieval")
        t_retrieval = time.perf_counter()
        filtered, trace = _PROVIDER.generate(context, active_journeys=active_journeys, guidelines=guidelines)
        retrieval_ms = (time.perf_counter() - t_retrieval) * 1000.0
        if collector is not None:
            collector.record_retrieval_pass(trace, retrieval_ms=retrieval_ms)
            if collector._matcher_calls == 0:
                collector.start_stage("judge_match")
        t_match = time.perf_counter()
        if (
            (os.environ.get("PARLANT_LOW_RISK_MATCHER_FAST_PATH") or "1").strip().lower()
            in {"1", "true", "yes", "on"}
            and getattr(trace, "enforcement_level", "medium") == "low"
        ):
            result = _fast_match_result(_PROVIDER, filtered, trace)
        else:
            result = await _ORIGINAL_MATCH(self, context, active_journeys, filtered)
        judge_match_ms = (time.perf_counter() - t_match) * 1000.0
        matcher_ids = _matcher_artifact_ids(_PROVIDER, result)
        if collector is not None:
            collector.record_match_pass(
                trace=trace,
                matcher_ids=matcher_ids,
                batch_count=getattr(result, "batch_count", None),
                judge_match_ms=judge_match_ms,
                filtered_count=len(filtered),
            )
        return result

    GuidelineMatcher.match_guidelines = patched_match_guidelines  # type: ignore[method-assign]
    _PATCH_APPLIED = True
    _logger.info(
        "candidate_provider: patched GuidelineMatcher.match_guidelines top_k=%s",
        settings.matching_top_k,
    )
