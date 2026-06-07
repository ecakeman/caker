from __future__ import annotations

import json
import os
from pathlib import Path

from app.telemetry.collector import TurnCollector
from app.telemetry.content_record import to_content_record
from app.telemetry.judge import judge_response
from app.telemetry.patches.material_output_protocol import render_material_protocol
from app.telemetry.schema import TELEMETRY_SCHEMA_VERSION
from app.telemetry.writer import (
    append_content_record,
    append_turn_record,
    content_record_path,
    read_turn_records,
    turn_pipeline_path,
)


def test_judge_flags_overpromise() -> None:
    j = judge_response(
        customer_query="能赔吗",
        agent_response="放心，一定赔给你，返佣也可以谈。",
        matched_guideline_ids=[],
        retrieval_topk_ids=[],
        active_journey_id=None,
        always_on_ok=True,
    )
    assert j.compliance_pass is False
    assert "overpromise_payout" in j.failure_reasons


def test_material_output_protocol_replaces_image_claim() -> None:
    text = "刚给你发了张图，里面讲了监管怎么兜底。\n\n线上买稳不稳，关键看合同。"
    rendered = render_material_protocol(text, tokens=["[图片:image50]"])
    assert rendered.startswith("[图片:image50]")
    assert "刚给你发" not in rendered
    assert "线上买稳不稳" in rendered


def test_material_output_protocol_strips_unbound_image_token() -> None:
    rendered = render_material_protocol("[图片:image50]\n\n这轮只是文字解释。", tokens=[])
    assert "[图片:image50]" not in rendered
    assert "这轮只是文字解释" in rendered


def test_material_output_protocol_removes_generic_sent_claim() -> None:
    rendered = render_material_protocol(
        "刚给你发了个测算，你瞅瞅这个量级\n\n具体还得看年龄。", tokens=["[图片:image53]"]
    )
    assert rendered.startswith("[图片:image53]")
    assert "刚给你发" not in rendered
    assert "具体还得看年龄" in rendered


def test_content_record_compact_no_noise() -> None:
    full = {
        "session_id": "s1",
        "trace_id": "t1",
        "turn_index": 2,
        "customer_query": "x" * 2000,
        "agent_response": "y" * 3000,
        "timing": {
            "e2e_ms": 900.0,
            "slowest_stage": "retrieval",
            "stages_ms": {"retrieval": 400.0, "judge_match": 200.0, "llm": 100.0},
            "llm": {"calls": 3, "total_tokens_sum": 1200},
            "tools": {"records": [{"tool_id": "lookup_policy", "success": True, "latency_ms": 12.0}]},
        },
        "retrieval": {"adaptive_k": 8},
        "journey": {"active_journey_id": "j1", "active_state_id": "st1"},
        "matched_guideline_ids": ["g1", "g2"],
        "matcher_input_guideline_ids_count": 5,
        "no_match_reason": "matcher_rejected_all",
        "always_on_injected_ids": ["a1"],
        "relationship_closure_added_ids": [],
        "response_judge": {
            "progress_pass": True,
            "compliance_pass": True,
            "grounded_pass": True,
            "failure_reasons": [],
        },
        "match": {"recall_at_k": 0.5},
        "wakeup_payload": {"noise": True},
        "recall_memorys": ["should not appear"],
    }
    row = to_content_record(full, run_id="run1", scenario_id="claim")
    assert "wakeup" not in json.dumps(row, ensure_ascii=False)
    assert "recall_memory" not in json.dumps(row, ensure_ascii=False)
    assert len(row["user_message"]) <= 501
    assert len(row["agent_reply"]) <= 801
    assert row["stage_ms_top3"][0]["stage"] == "retrieval"
    assert row["matched_guideline_ids_topN"] == ["g1", "g2"]
    line = json.dumps(row, ensure_ascii=False)
    assert len(line.encode("utf-8")) < 4096


def test_turn_pipeline_jsonl_debug_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TELEMETRY_LEVEL", raising=False)
    record = {
        "v": TELEMETRY_SCHEMA_VERSION,
        "session_id": "sess1",
        "trace_id": "trace1",
        "turn_index": 1,
        "timing": {"e2e_ms": 1200.0, "stages_ms": {"retrieval": 100.0}},
        "response_judge": {"quality_score": 80.0, "failure_reasons": []},
    }
    append_turn_record(record, root=tmp_path)
    path = turn_pipeline_path(tmp_path)
    assert path.is_file()
    rows = read_turn_records(path, session_id="sess1")
    assert len(rows) == 1
    assert rows[0]["trace_id"] == "trace1"


def test_collector_finalize_writes_content_record(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TELEMETRY_LEVEL", raising=False)
    c = TurnCollector(root=tmp_path, bundle=None)
    c.session_id = "s"
    c.trace_id = "t"
    c.turn_index = 1
    c.customer_query = "你好"
    c.agent_response = "这是足够长的回复，包含保单与理赔材料说明，帮助客户理解报案流程和医院发票要求。"
    out = c.finalize()
    assert out is not None
    rows = read_turn_records(content_record_path(tmp_path))
    assert len(rows) == 1
    assert rows[0]["progress_pass"] is True
    assert not turn_pipeline_path(tmp_path).is_file()


def test_collector_finalize_writes_debug_pipeline(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TELEMETRY_LEVEL", "debug")
    c = TurnCollector(root=tmp_path, bundle=None)
    c.session_id = "s"
    c.trace_id = "t"
    c.turn_index = 1
    c.customer_query = "你好"
    c.agent_response = "回复"
    c.finalize()
    assert content_record_path(tmp_path).is_file()
    assert turn_pipeline_path(tmp_path).is_file()


def test_append_content_record_roundtrip(tmp_path: Path) -> None:
    row = {"session_id": "x", "turn": 1, "e2e_ms": 1.0}
    append_content_record(row, root=tmp_path)
    rows = read_turn_records(content_record_path(tmp_path), session_id="x")
    assert rows[0]["turn"] == 1
