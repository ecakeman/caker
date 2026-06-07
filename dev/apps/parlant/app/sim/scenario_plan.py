from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from app.artifacts import ArtifactBundle

# Multi-scenario 20-turn: curated scenario segments (scenario_id, turns in segment).
CURATED_MULTISCENARIO: list[tuple[str, int]] = [
    ("claim_service_after_purchase", 5),
    ("compliance_rebate_pressure", 4),
    ("medical_vs_ci", 4),
    ("online_claim_trust", 4),
    ("intro_cold_start", 3),
]

SCENARIOS_PATH = Path(__file__).resolve().parents[2] / "data" / "sim_scenarios" / "scenarios.json"


def load_scenarios(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or SCENARIOS_PATH
    if not p.is_file():
        raise FileNotFoundError(f"scenario bank missing: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError(f"scenario bank empty: {p}")
    return data


def choose_scenario(scenarios: list[dict[str, Any]], scenario_id: str) -> dict[str, Any]:
    if scenario_id == "random":
        return random.choice(scenarios)
    for s in scenarios:
        if s.get("id") == scenario_id:
            return s
    known = ", ".join(str(s.get("id")) for s in scenarios)
    raise ValueError(f"unknown scenario {scenario_id!r}; known: {known}")


def _abm_assertions(bundle: ArtifactBundle, scenario: dict[str, Any]) -> dict[str, Any]:
    jid = scenario.get("target_journey")
    scope = bundle.scope_map
    out: dict[str, Any] = {"expected_journey_id": jid}
    if jid:
        out["expected_guideline_ids"] = list((scope.get("journey_scoped") or {}).get(jid, [])[:8])
    sid = scenario.get("id") or ""
    if "compliance" in sid or "rebate" in sid:
        out["always_on_required"] = True
        out["expected_guideline_ids"] = list(scope.get("always_on") or [])[:8]
    if "claim" in sid or "online" in sid:
        out["expected_tools"] = ["send_image", "send_link"]
    if "medical_vs" in sid:
        out["expected_relationship_types"] = ["disambiguation", "priority"]
    if "policy_review" in sid or "old_policy" in sid:
        out["requires_retrieval"] = True
    return out


def build_single_scenario_plan(
    bundle: ArtifactBundle,
    scenario: dict[str, Any],
    *,
    turns: int = 20,
) -> list[dict[str, Any]]:
    abm = _abm_assertions(bundle, scenario)
    plan: list[dict[str, Any]] = []
    for i in range(turns):
        plan.append(
            {
                "turn_index": i + 1,
                "scenario_id": scenario.get("id"),
                "scenario_type": "scenario_bank",
                "segment_turn": i + 1,
                "segment_turns": turns,
                "scenario": scenario,
                "must_cover": scenario.get("must_cover") or [],
                "abm_assertions": abm,
            }
        )
    return plan


def build_multiscenario_plan(
    bundle: ArtifactBundle,
    scenarios: list[dict[str, Any]],
    *,
    turns: int = 20,
) -> list[dict[str, Any]]:
    by_id = {s["id"]: s for s in scenarios}
    segments: list[tuple[dict[str, Any], int]] = []
    total = 0
    for sid, n in CURATED_MULTISCENARIO:
        if sid not in by_id:
            continue
        segments.append((by_id[sid], n))
        total += n
    if total < turns:
        for s in scenarios:
            if s["id"] not in {x[0]["id"] for x in segments}:
                segments.append((s, 2))
                total += 2
            if total >= turns:
                break
    plan: list[dict[str, Any]] = []
    turn_index = 0
    for scenario, seg_turns in segments:
        if turn_index >= turns:
            break
        n = min(seg_turns, turns - turn_index)
        abm = _abm_assertions(bundle, scenario)
        for i in range(n):
            turn_index += 1
            plan.append(
                {
                    "turn_index": turn_index,
                    "scenario_id": scenario.get("id"),
                    "scenario_type": "scenario_bank",
                    "segment_turn": i + 1,
                    "segment_turns": n,
                    "scenario": scenario,
                    "must_cover": scenario.get("must_cover") or [],
                    "abm_assertions": abm,
                }
            )
    return plan[:turns]


def build_scenario_turn_plan(
    bundle: ArtifactBundle,
    *,
    scenario_id: str = "multiscenario",
    turns: int = 20,
    scenarios_path: Path | None = None,
) -> list[dict[str, Any]]:
    scenarios = load_scenarios(scenarios_path)
    if scenario_id in ("multiscenario", "multi"):
        return build_multiscenario_plan(bundle, scenarios, turns=turns)
    scenario = choose_scenario(scenarios, scenario_id)
    return build_single_scenario_plan(bundle, scenario, turns=turns)


def write_plan(path: Any, plan: list[dict[str, Any]]) -> None:
    serializable = []
    for row in plan:
        item = dict(row)
        if "scenario" in item:
            item["scenario_snapshot"] = {
                "id": item["scenario"].get("id"),
                "topic": item["scenario"].get("topic"),
                "target_journey": item["scenario"].get("target_journey"),
            }
        serializable.append(item)
    path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
