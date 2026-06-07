from __future__ import annotations

from app.config import load_settings
from app.matching.relationships import apply_relationship_closure
from app.runtime.guideline_registry import GuidelineRegistry


def test_dependency_closure_adds_parent() -> None:
    closed, trace = apply_relationship_closure(
        ["ag_e8a9d38efbcc0137"],
        [
            {
                "type": "dependency",
                "source_id": "ag_e8a9d38efbcc0137",
                "target_id": "ag_1b44c1eb6a4193dd",
                "reason": "topic_underwriting_baseline",
            }
        ],
    )
    assert "ag_1b44c1eb6a4193dd" in closed
    assert any(t.get("action") == "dependency_add" for t in trace)


def test_guideline_registry_maps_normalized_rows() -> None:
    rows = [
        {
            "guideline_id": "ag_test123",
            "condition_text": "条件A",
            "action_text": "动作A",
        }
    ]
    reg = GuidelineRegistry(rows)
    assert reg._by_key[("条件A", "动作A")] == "ag_test123"


def test_candidate_provider_patch_enabled_by_default() -> None:
    import os

    from app.runtime.matcher_patch import _enabled

    prev = os.environ.get("PARLANT_CANDIDATE_PROVIDER")
    try:
        os.environ.pop("PARLANT_CANDIDATE_PROVIDER", None)
        assert _enabled() is True
        os.environ["PARLANT_CANDIDATE_PROVIDER"] = "0"
        assert _enabled() is False
    finally:
        if prev is None:
            os.environ.pop("PARLANT_CANDIDATE_PROVIDER", None)
        else:
            os.environ["PARLANT_CANDIDATE_PROVIDER"] = prev


def test_settings_load_for_provider() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    settings = load_settings(root)
    assert settings.matching_top_k >= 3
