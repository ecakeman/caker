from __future__ import annotations

import json
from pathlib import Path

from app.artifacts import load_artifacts
from app.config import load_settings
from app.sim.scenario_plan import build_scenario_turn_plan, load_scenarios


def test_manifest_v2_required_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "artifacts/manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("pipeline_version") == "2"
    paths = manifest["paths"]
    for key in (
        "variables",
        "canned_responses",
        "glossary",
        "retriever_corpus",
        "retrieval_config",
        "audit_extended",
    ):
        assert key in paths
        assert (root / paths[key]).exists() or (root / paths[key]).is_dir()


def test_load_artifacts_v2_bundle() -> None:
    root = Path(__file__).resolve().parents[1]
    bundle = load_artifacts(load_settings(root).artifacts_root)
    assert bundle.variables.get("variables")
    assert bundle.glossary.get("terms")
    assert bundle.retrieval_config.get("retrieval")
    assert len(bundle.relationships) >= 10


def test_scenario_plan_20_turns() -> None:
    root = Path(__file__).resolve().parents[1]
    bundle = load_artifacts(load_settings(root).artifacts_root)
    scenarios = load_scenarios(root / "data" / "sim_scenarios" / "scenarios.json")
    assert len(scenarios) >= 10
    plan = build_scenario_turn_plan(bundle, scenario_id="claim_service_after_purchase", turns=20)
    assert len(plan) == 20
    assert plan[0]["scenario"]["id"] == "claim_service_after_purchase"
    assert plan[0].get("customer_profile") is None
    assert "customer_profile" in plan[0]["scenario"]
    multi = build_scenario_turn_plan(bundle, scenario_id="multiscenario", turns=20)
    assert len(multi) == 20
    ids = {p["scenario_id"] for p in multi}
    assert "claim_service_after_purchase" in ids
    assert "compliance_rebate_pressure" in ids
