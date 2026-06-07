from __future__ import annotations

from data_pipeline.relationships import detect_relationship_cycles
from data_pipeline.tool_guidelines import enrich_guideline_tool_metadata


def test_tool_guideline_enrichment() -> None:
    guidelines = [
        {
            "guideline_id": "ag_test",
            "condition_text": "客户想看监管说明图",
            "action_text": "调用 send_image",
            "tools": ["send_image"],
            "tool_actions": [{"tool": "send_image", "topic": "监管说明图"}],
            "scope": "global",
            "journey_id": None,
            "state_id": None,
        }
    ]
    stats = enrich_guideline_tool_metadata(guidelines)
    g = guidelines[0]
    assert g["is_tool_trigger"] is True
    assert "topic" in g["required_params"]
    assert g["preferred_scope"] == "global"
    assert stats["tool_trigger_count"] == 1


def test_relationship_cycle_detection() -> None:
    edges = [
        {"type": "entailment", "source_id": "a", "target_id": "b"},
        {"type": "dependency", "source_id": "b", "target_id": "c"},
        {"type": "entailment", "source_id": "c", "target_id": "a"},
    ]
    cycles = detect_relationship_cycles(edges)
    assert len(cycles) >= 1
