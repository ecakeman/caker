from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.telemetry.pipeline_link import (
    build_candidate_entries,
    compute_no_match_reason,
    relationship_closure_added_ids,
)


@dataclass
class FakeTrace:
    bm25_top_ids: list[str] = field(default_factory=list)
    vector_top_ids: list[str] = field(default_factory=list)
    rrf_candidates: list[dict[str, Any]] = field(default_factory=list)
    reranked: list[dict[str, Any]] = field(default_factory=list)
    always_on_injected: list[str] = field(default_factory=list)
    after_relationships: list[str] = field(default_factory=list)
    relationship_trace: list[dict[str, Any]] = field(default_factory=list)


def test_build_candidate_entries_sources_and_order():
    trace = FakeTrace(
        bm25_top_ids=["g1"],
        vector_top_ids=["g2"],
        rrf_candidates=[
            {"guideline_id": "g1", "rrf_score": 0.5},
            {"guideline_id": "g2", "rrf_score": 0.4},
        ],
        reranked=[
            {"guideline_id": "g1", "rerank_score": 0.9, "rrf_score": 0.5},
        ],
        always_on_injected=["g3"],
        after_relationships=["g1", "g3", "g2"],
    )
    entries = build_candidate_entries(trace)
    assert [e["guideline_id"] for e in entries] == ["g1", "g3", "g2"]
    g1 = next(e for e in entries if e["guideline_id"] == "g1")
    assert "bm25" in g1["sources"]
    assert "vector" in g1["sources"] or "rrf" in g1["sources"]
    assert "rerank" in g1["sources"]
    g3 = next(e for e in entries if e["guideline_id"] == "g3")
    assert "always_on" in g3["sources"]


def test_relationship_closure_added_ids():
    trace = FakeTrace(
        relationship_trace=[
            {"action": "dependency_add", "target": "g9"},
            {"action": "always_on_force", "target": "g0"},
            {"action": "other"},
        ]
    )
    assert relationship_closure_added_ids(trace) == ["g9", "g0"]


def test_compute_no_match_reason_enum():
    assert (
        compute_no_match_reason(
            candidate_ids=[],
            matcher_input_count=0,
            matcher_input_ids=[],
            matched_ids=[],
            matcher_invocations=1,
        )
        == "candidate_empty"
    )
    assert (
        compute_no_match_reason(
            candidate_ids=["g1"],
            matcher_input_count=0,
            matcher_input_ids=[],
            matched_ids=[],
            matcher_invocations=1,
        )
        == "filtered_empty"
    )
    assert (
        compute_no_match_reason(
            candidate_ids=["g1"],
            matcher_input_count=3,
            matcher_input_ids=["g1", "g2", "g3"],
            matched_ids=[],
            matcher_invocations=2,
        )
        == "matcher_rejected_all"
    )
    assert (
        compute_no_match_reason(
            candidate_ids=["g1"],
            matcher_input_count=2,
            matcher_input_ids=["g1"],
            matched_ids=["g1"],
            matcher_invocations=1,
        )
        == "matched"
    )
