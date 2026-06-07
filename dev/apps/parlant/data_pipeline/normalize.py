from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from data_pipeline.ids import content_hash, guideline_id, journey_id
from data_pipeline.schema import schema_contract, validate_guidelines, validate_journeys
from data_pipeline.tool_guidelines import enrich_guideline_tool_metadata


def _infer_duration(action: str) -> str:
    if re.search(r"(一直|始终|全程|每次|always)", action):
        return "continuous"
    if re.search(r"(确认|追问|直到|核实|再次)", action):
        return "persistent"
    return "one_off"


def _infer_risk(condition: str, action: str) -> str:
    text = f"{condition} {action}"
    if any(k in text for k in ("合规", "返佣", "监管", "违法", "诈骗", "误导")):
        return "high"
    if any(k in text for k in ("健康告知", "核保", "拒保", "如实告知", "理赔")):
        return "medium"
    return "low"


def normalize_guidelines(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in raw:
        condition = (item.get("condition") or "").strip()
        action = (item.get("action") or "").strip()
        gid = guideline_id(condition, action)
        broker_jid = (item.get("broker_journey_id") or "").strip()
        bucket = (item.get("parlant_bucket") or "").strip()
        scope = "journey_scoped" if broker_jid or bucket == "per_journey" else "global"
        out.append(
            {
                "guideline_id": gid,
                "broker_source_id": (item.get("source_id") or "").strip() or None,
                "condition_text": condition,
                "action_text": action,
                "tools": list(item.get("tools") or []),
                "tool_actions": list(item.get("tool_actions") or []),
                "scope": scope,
                "journey_id": broker_jid or None,
                "state_id": None,
                "risk_level": _infer_risk(condition, action),
                "once_or_repeat": _infer_duration(action),
                "parlant_bucket": bucket or None,
                "source_hash": content_hash(condition, action),
                "condition": condition,
                "action": action,
            }
        )
    return out


def normalize_journeys(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in raw:
        jid = (item.get("journey_id") or "").strip() or journey_id(item.get("title") or "")
        states = []
        for s in item.get("states") or []:
            states.append(
                {
                    "state_id": s["state_id"],
                    "state_kind": s.get("state_kind"),
                    "chat_instruction": s.get("chat_instruction"),
                    "tool_name": s.get("tool_name"),
                    "tool_instruction": s.get("tool_instruction"),
                }
            )
        transitions = []
        for i, t in enumerate(item.get("transitions") or []):
            transitions.append(
                {
                    "transition_id": f"t_{i:04d}",
                    "from_state": t.get("from_state"),
                    "to_state": t.get("to_state"),
                    "transition_kind": t.get("transition_kind"),
                    "condition_text": t.get("condition_text"),
                }
            )
        out.append(
            {
                "journey_id": jid,
                "title": item.get("title"),
                "description": item.get("description", ""),
                "activation_conditions": list(item.get("conditions") or []),
                "states": states,
                "transitions": transitions,
                "conditions": item.get("conditions") or [],
            }
        )
    return out


def write_normalized(
    guidelines_path: Path,
    journeys_path: Path,
    out_dir: Path,
) -> dict[str, Any]:
    raw_g = json.loads(guidelines_path.read_text(encoding="utf-8"))
    raw_j = json.loads(journeys_path.read_text(encoding="utf-8"))
    norm_g = normalize_guidelines(raw_g)
    tool_meta = enrich_guideline_tool_metadata(norm_g)
    norm_j = normalize_journeys(raw_j)
    g_errors = validate_guidelines(norm_g)
    j_errors = validate_journeys(norm_j)
    if g_errors or j_errors:
        raise ValueError("Normalized schema validation failed: " + "; ".join(g_errors + j_errors))
    out_dir.mkdir(parents=True, exist_ok=True)
    schema_path = out_dir.parent / "schema_contract.json"
    schema_path.write_text(json.dumps(schema_contract(), ensure_ascii=False, indent=2), encoding="utf-8")
    g_path = out_dir / "guidelines.json"
    j_path = out_dir / "journeys.json"
    g_path.write_text(json.dumps(norm_g, ensure_ascii=False, indent=2), encoding="utf-8")
    j_path.write_text(json.dumps(norm_j, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "tool_governance": tool_meta,
        "guideline_count": len(norm_g),
        "journey_count": len(norm_j),
        "guidelines_path": str(g_path),
        "journeys_path": str(j_path),
        "source_guidelines_hash": content_hash(guidelines_path.read_text(encoding="utf-8")),
        "source_journeys_hash": content_hash(journeys_path.read_text(encoding="utf-8")),
        "schema_contract_path": str(schema_path),
    }
