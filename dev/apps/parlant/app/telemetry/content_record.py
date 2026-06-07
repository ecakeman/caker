from __future__ import annotations

import copy
import json
import re
from typing import Any

NOISE_KEY_RE = re.compile(
    r"(wakeup|recall_memory|forced_recall|prompt_dump|artifacts_blob)",
    re.IGNORECASE,
)
NOISE_VALUE_RE = re.compile(
    r"(wakeup|recall_memorys?|forced_recall)",
    re.IGNORECASE,
)

_TRUNC_USER = 500
_TRUNC_AGENT = 800
_MATERIAL_TOKEN_RE = re.compile(r"\[(?:图片|链接|引用):[A-Za-z0-9_\-:.]+\]|\[暂无可用图片\]")


def _trunc(text: str, n: int) -> str:
    t = (text or "").strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def _top_stages(stages_ms: dict[str, Any], n: int = 3) -> list[dict[str, float | str]]:
    pairs: list[tuple[str, float]] = []
    for name, ms in (stages_ms or {}).items():
        try:
            pairs.append((str(name), float(ms)))
        except (TypeError, ValueError):
            continue
    pairs.sort(key=lambda x: x[1], reverse=True)
    return [{"stage": k, "ms": round(v, 2)} for k, v in pairs[:n]]


def _tools_called(tools: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rec in tools.get("records") or []:
        if not isinstance(rec, dict):
            continue
        out.append(
            {
                "name": str(rec.get("tool_id") or "unknown"),
                "tool_call_id": rec.get("tool_call_id"),
                "ok": bool(rec.get("success", True)),
                "ms": round(float(rec.get("latency_ms") or 0), 2),
                "error_type": rec.get("error_type"),
                "error_msg": _trunc(str(rec.get("error_msg") or rec.get("error") or ""), 240),
                "input_summary": rec.get("input_summary") or {},
                "status_code": rec.get("status_code"),
                "output_url": rec.get("output_url"),
                "attachment_id": rec.get("attachment_id"),
                "fallback_no_image": bool(rec.get("fallback_no_image")),
            }
        )
    return out


def to_content_record(
    full: dict[str, Any],
    *,
    run_id: str = "",
    scenario_id: str = "",
    session_event_count: int | None = None,
) -> dict[str, Any]:
    timing = full.get("timing") or {}
    llm = timing.get("llm") or {}
    journey = full.get("journey") or {}
    retrieval = full.get("retrieval") or {}
    matched = list(full.get("matched_guideline_ids") or [])
    pre_j = journey.get("pre_journey_id")
    post_j = journey.get("active_journey_id") or journey.get("post_journey_id")
    transition = None
    if journey.get("transitioned") and (pre_j or post_j):
        transition = {"from": pre_j, "to": post_j}

    return {
        "run_id": run_id,
        "session_id": full.get("session_id"),
        "trace_id": full.get("trace_id"),
        "turn": int(full.get("turn_index") or 0),
        "scenario_id": scenario_id,
        "user_message": _trunc(str(full.get("customer_query") or ""), _TRUNC_USER),
        "agent_reply": _trunc(str(full.get("agent_response") or ""), _TRUNC_AGENT),
        "e2e_ms": timing.get("e2e_ms"),
        "slowest_stage": timing.get("slowest_stage") or "",
        "stage_ms_top3": _top_stages(timing.get("stages_ms") or {}),
        "candidate_count": len(full.get("candidate_guideline_ids") or []),
        "matcher_in_count": int(full.get("matcher_input_guideline_ids_count") or 0),
        "matched_count": len(matched),
        "no_match_reason": full.get("no_match_reason"),
        "matched_guideline_ids_topN": matched[:5],
        "active_journey_id": post_j,
        "active_state_id": journey.get("active_state_id"),
        "state_transition": transition,
        "tools_called": _tools_called(timing.get("tools") or {}),
        "rendered_material_tokens": _MATERIAL_TOKEN_RE.findall(str(full.get("agent_response") or "")),
        "llm_calls": int(llm.get("calls") or 0),
        "total_tokens": int(llm.get("total_tokens_sum") or 0),
        "enforcement_calls_count": int((timing.get("enforcement") or {}).get("calls_count") or 0),
        "enforcement_tokens_total": int((timing.get("enforcement") or {}).get("tokens_total") or 0),
        "enforcement_level": retrieval.get("enforcement_level"),
        "K": retrieval.get("adaptive_k"),
        "always_on_count": len(full.get("always_on_injected_ids") or []),
        "closure_added_count": len(full.get("relationship_closure_added_ids") or []),
        "session_event_count": session_event_count,
        "progress_pass": (full.get("response_judge") or {}).get("progress_pass"),
        "compliance_pass": (full.get("response_judge") or {}).get("compliance_pass"),
        "grounded_pass": (full.get("response_judge") or {}).get("grounded_pass"),
        "quality_score": (full.get("response_judge") or {}).get("quality_score"),
        "failure_reasons": (full.get("response_judge") or {}).get("failure_reasons") or [],
        "recall_at_k": (full.get("match") or {}).get("recall_at_k"),
    }


def _strip_noise_obj(obj: Any) -> Any:
    if isinstance(obj, dict):
        cleaned: dict[str, Any] = {}
        for k, v in obj.items():
            if NOISE_KEY_RE.search(str(k)):
                continue
            if isinstance(v, str) and len(v) > 4000 and NOISE_VALUE_RE.search(v):
                continue
            cleaned[k] = _strip_noise_obj(v)
        return cleaned
    if isinstance(obj, list):
        return [_strip_noise_obj(x) for x in obj if not (isinstance(x, str) and NOISE_VALUE_RE.search(x))]
    if isinstance(obj, str) and len(obj) > 8000:
        return obj[:8000] + "…"
    return obj


def to_debug_record(full: dict[str, Any]) -> dict[str, Any]:
    rec = copy.deepcopy(full)
    rec.pop("pipeline_link", None)
    return _strip_noise_obj(rec)
