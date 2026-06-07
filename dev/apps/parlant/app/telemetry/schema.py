"""Turn pipeline observability schema (speed + accuracy, one JSONL row per turn)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


TELEMETRY_SCHEMA_VERSION = "2"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class LlmCallRecord:
    stage: str
    schema_name: str
    model: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    retries: int = 0
    error: str | None = None


@dataclass
class ToolCallRecord:
    tool_id: str
    latency_ms: float
    success: bool
    retries: int = 0
    error: str | None = None


@dataclass
class RetrievalHit:
    guideline_id: str
    source: str
    score: float
    rank: int


@dataclass
class ResponseJudge:
    progress_pass: bool
    compliance_pass: bool
    grounded_pass: bool
    quality_score: float
    failure_reasons: list[str] = field(default_factory=list)


@dataclass
class TurnPipelineRecord:
    v: str = TELEMETRY_SCHEMA_VERSION
    ts: str = ""
    session_id: str = ""
    trace_id: str = ""
    turn_index: int = 0
    offset: int | None = None
    customer_query: str = ""
    agent_response: str = ""

    timing: dict[str, Any] = field(default_factory=dict)
    retrieval: dict[str, Any] = field(default_factory=dict)
    match: dict[str, Any] = field(default_factory=dict)
    journey: dict[str, Any] = field(default_factory=dict)
    response_judge: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def empty_timing() -> dict[str, Any]:
    return {
        "e2e_ms": 0.0,
        "stages_ms": {
            "context_build": 0.0,
            "retrieval": 0.0,
            "judge_match": 0.0,
            "arq_enforcement": 0.0,
            "tools": 0.0,
            "compose": 0.0,
            "writeback": 0.0,
        },
        "slowest_stage": "",
        "llm": {
            "calls": 0,
            "prompt_tokens_sum": 0,
            "completion_tokens_sum": 0,
            "total_tokens_sum": 0,
            "prompt_tokens_avg": 0.0,
            "total_tokens_avg": 0.0,
            "latency_ms_total": 0.0,
            "retries": 0,
            "calls_detail": [],
        },
        "tools": {
            "calls": 0,
            "latency_ms_total": 0.0,
            "failures": 0,
            "retries": 0,
            "records": [],
        },
    }


def empty_retrieval() -> dict[str, Any]:
    return {
        "query_original": "",
        "query_rewritten": None,
        "scope_pool_size": None,
        "adaptive_k": 0,
        "counts": {
            "scope_pool": 0,
            "bm25": 0,
            "vector": 0,
            "rrf": 0,
            "reranked": 0,
            "relationship_added": 0,
            "always_on_injected": 0,
            "matcher_input": 0,
            "matcher_output": 0,
        },
        "topk": [],
        "always_on_required": [],
        "always_on_present": [],
        "always_on_ok": True,
        "relationship_trace": [],
    }


def empty_match() -> dict[str, Any]:
    return {
        "matched_guideline_ids": [],
        "matcher_batches": 0,
        "matcher_match_count": 0,
        "false_positive_ids": [],
        "false_negative_ids": [],
        "journey_pool_ids": [],
        "recall_at_k": None,
    }


def empty_journey() -> dict[str, Any]:
    return {
        "active_journey_id": None,
        "active_state_id": None,
        "journey_titles": [],
        "transitioned": False,
        "stuck": False,
        "pre_journey_id": None,
        "post_journey_id": None,
    }
