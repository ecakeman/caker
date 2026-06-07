from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_variables_schema(
    guidelines: list[dict[str, Any]],
    journeys: list[dict[str, Any]],
) -> dict[str, Any]:
    """A2: profile_* vs state_* layered variables for deterministic matching."""
    variables: list[dict[str, Any]] = [
        {
            "name": "profile_customer_facts",
            "layer": "profile",
            "type": "object",
            "description": "Broker-side customer facts captured during session",
            "source": "tool",
            "refresh_strategy": "on_tool_write",
            "default": {},
            "updatable_by_tools": ["record_customer_facts"],
            "readable_by_tools": ["read_customer_facts"],
        },
        {
            "name": "profile_risk_flags",
            "layer": "profile",
            "type": "object",
            "description": "Session-level risk markers (rebate pressure, overpromise attempts)",
            "source": "runtime",
            "refresh_strategy": "on_turn",
            "default": {},
        },
    ]
    state_markers = [
        ("state_missing_params", "Tool call blocked: required params not yet collected"),
        ("state_user_declined", "Customer declined to provide requested info"),
        ("state_matcher_rejected_streak", "Consecutive matcher_rejected_all count in session"),
        ("state_active_journey", "Current active journey id"),
        ("state_active_state", "Current active journey state id"),
    ]
    for name, desc in state_markers:
        variables.append(
            {
                "name": name,
                "layer": "state",
                "type": "string",
                "description": desc,
                "source": "runtime",
                "refresh_strategy": "on_turn",
                "default": None,
            }
        )

    tool_names: set[str] = set()
    for g in guidelines:
        if g.get("is_tool_trigger"):
            for t in g.get("tools") or []:
                tool_names.add(str(t))
    for j in journeys:
        for st in j.get("states") or []:
            if st.get("tool_name"):
                tool_names.add(str(st["tool_name"]))
            sid = st.get("state_id")
            if not sid:
                continue
            variables.append(
                {
                    "name": f"state_journey::{j['journey_id']}::{sid}",
                    "layer": "state",
                    "type": "enum",
                    "description": f"Active state marker for {j.get('title') or j['journey_id']}",
                    "source": "journey_runtime",
                    "refresh_strategy": "on_journey_transition",
                    "default": None,
                    "journey_id": j["journey_id"],
                    "state_id": sid,
                }
            )

    profile_count = sum(1 for v in variables if v.get("layer") == "profile")
    state_count = sum(1 for v in variables if v.get("layer") == "state")
    return {
        "version": "2",
        "variables": variables,
        "layers": {"profile": profile_count, "state": state_count},
        "stats": {
            "total": len(variables),
            "profile_vars": profile_count,
            "state_vars": state_count,
            "tool_derived": len(tool_names),
            "journey_state_markers": sum(1 for v in variables if v.get("source") == "journey_runtime"),
        },
    }


def write_variables(guidelines_path: Path, journeys_path: Path, out_path: Path) -> dict[str, Any]:
    guidelines = json.loads(guidelines_path.read_text(encoding="utf-8"))
    journeys = json.loads(journeys_path.read_text(encoding="utf-8"))
    doc = build_variables_schema(guidelines, journeys)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"variables_path": str(out_path), **doc["stats"]}
