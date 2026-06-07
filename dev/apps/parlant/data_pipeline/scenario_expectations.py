from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_TAG_MAP = {
    "重疾": "critical_illness",
    "医疗": "medical",
    "核保": "underwriting",
    "理赔": "claims",
    "返佣": "compliance",
    "合规": "compliance",
    "少儿": "child",
    "父母": "senior",
    "保单": "policy_review",
    "对比": "compare",
    "停售": "urgency",
    "肺结节": "underwriting",
    "甲状腺": "underwriting",
}


def _tags_from_scenario(scenario: dict[str, Any]) -> list[str]:
    text = " ".join(
        [
            str(scenario.get("topic") or ""),
            str(scenario.get("opening_intent") or ""),
            " ".join(scenario.get("must_cover") or []),
            " ".join(scenario.get("trigger_conditions") or []),
        ]
    )
    tags: set[str] = set()
    for k, v in _TAG_MAP.items():
        if k in text:
            tags.add(v)
    if scenario.get("target_journey"):
        tags.add(str(scenario["target_journey"]))
    return sorted(tags)


def _expected_tools(scenario: dict[str, Any]) -> list[str]:
    cues = " ".join(scenario.get("material_cues") or [])
    tools: list[str] = []
    if any(k in cues for k in ("图", "截图", "对比表", "说明图")):
        tools.append("send_image")
    if any(k in cues for k in ("链接", "URL", "投保")):
        tools.append("send_link")
    return tools


def build_scenario_expectations(
    scenarios: list[dict[str, Any]],
    *,
    guidelines: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A5: minimal labeled expectations per scenario for recall@K_on_labeled."""
    tool_guidelines = [g["guideline_id"] for g in (guidelines or []) if g.get("is_tool_trigger")]
    by_tag: dict[str, list[str]] = {}
    for g in guidelines or []:
        gid = g["guideline_id"]
        text = f"{g.get('condition_text', '')} {g.get('action_text', '')}"
        for k, tag in _TAG_MAP.items():
            if k in text:
                by_tag.setdefault(tag, []).append(gid)

    out: dict[str, Any] = {}
    for s in scenarios:
        sid = str(s.get("id") or "")
        if not sid:
            continue
        tags = _tags_from_scenario(s)
        expected_gids: list[str] = []
        for tag in tags:
            expected_gids.extend(by_tag.get(tag, [])[:5])
        if _expected_tools(s):
            for g in guidelines or []:
                if g.get("is_tool_trigger") and any(t in (g.get("tools") or []) for t in _expected_tools(s)):
                    expected_gids.append(g["guideline_id"])
        expected_gids = sorted(set(expected_gids))[:12]
        out[sid] = {
            "expected_tags": tags,
            "expected_guideline_ids": expected_gids,
            "expected_tool_calls": _expected_tools(s),
            "tool_scenario": bool(s.get("material_cues")),
            "high_risk": bool(re.search(r"返佣|合规|监管", str(s.get("topic", "")) + str(s.get("id", "")))),
            "target_journey": s.get("target_journey"),
        }
    return {
        "version": "1",
        "scenarios": out,
        "stats": {
            "scenario_count": len(out),
            "tool_scenario_count": sum(1 for v in out.values() if v.get("tool_scenario")),
            "high_risk_count": sum(1 for v in out.values() if v.get("high_risk")),
            "tool_guideline_pool_size": len(tool_guidelines),
        },
    }


def write_scenario_expectations(
    scenarios_path: Path,
    out_path: Path,
    *,
    guidelines_path: Path | None = None,
) -> dict[str, Any]:
    scenarios = json.loads(scenarios_path.read_text(encoding="utf-8"))
    guidelines = None
    if guidelines_path and guidelines_path.is_file():
        guidelines = json.loads(guidelines_path.read_text(encoding="utf-8"))
    doc = build_scenario_expectations(scenarios, guidelines=guidelines)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"expectations_path": str(out_path), **doc["stats"]}
