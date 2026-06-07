from __future__ import annotations

import re
from typing import Any

from app.telemetry.schema import ResponseJudge

_FORBIDDEN_PATTERNS = [
    (r"一定赔|保证赔|100%赔", "overpromise_payout"),
    (r"返佣|返钱|回扣", "rebate_offer"),
    (r"代签|代填|规避健康告知", "compliance_bypass"),
    (r"跳过官方流程", "skip_official_process"),
]

_VAGUE_PATTERNS = [
    r"^收到[。.!！]?$",
    r"^好的[。.!！]?$",
    r"^嗯[。.!！]?$",
]


def _has_substance(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 30:
        return False
    for pat in _VAGUE_PATTERNS:
        if re.match(pat, t):
            return False
    return True


def judge_response(
    *,
    customer_query: str,
    agent_response: str,
    matched_guideline_ids: list[str],
    retrieval_topk_ids: list[str],
    active_journey_id: str | None,
    always_on_ok: bool,
) -> ResponseJudge:
    reasons: list[str] = []
    response = (agent_response or "").strip()
    query = (customer_query or "").strip()

    progress_pass = bool(query) and _has_substance(response)
    if not progress_pass:
        reasons.append("low_substance_or_no_progress")

    compliance_pass = True
    for pat, code in _FORBIDDEN_PATTERNS:
        if re.search(pat, response):
            compliance_pass = False
            reasons.append(code)

    grounded_pass = bool(matched_guideline_ids) or bool(retrieval_topk_ids)
    if not grounded_pass and len(response) > 80:
        grounded_pass = any(
            kw in response for kw in ("保单", "理赔", "报案", "材料", "医院", "发票", "合规")
        )
    if not grounded_pass:
        reasons.append("weak_grounding")

    if not always_on_ok:
        reasons.append("always_on_missing")

    if active_journey_id and not matched_guideline_ids:
        reasons.append("journey_active_no_match")
        # caller may override via no_match_reason in pipeline_link

    score = 100.0
    if not progress_pass:
        score -= 35
    if not compliance_pass:
        score -= 40
    if not grounded_pass:
        score -= 20
    if not always_on_ok:
        score -= 15
    score = max(0.0, min(100.0, score))

    return ResponseJudge(
        progress_pass=progress_pass,
        compliance_pass=compliance_pass,
        grounded_pass=grounded_pass,
        quality_score=round(score, 1),
        failure_reasons=sorted(set(reasons)),
    )


def judge_to_dict(judge: ResponseJudge) -> dict[str, Any]:
    return {
        "progress_pass": judge.progress_pass,
        "compliance_pass": judge.compliance_pass,
        "grounded_pass": judge.grounded_pass,
        "quality_score": judge.quality_score,
        "failure_reasons": judge.failure_reasons,
    }
