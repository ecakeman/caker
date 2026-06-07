from __future__ import annotations

from typing import Any

GUIDELINE_SCHEMA_VERSION = "1"
JOURNEY_SCHEMA_VERSION = "1"

REQUIRED_GUIDELINE_FIELDS = (
    "guideline_id",
    "condition_text",
    "action_text",
    "tools",
    "scope",
    "risk_level",
    "once_or_repeat",
    "source_hash",
)

REQUIRED_JOURNEY_FIELDS = (
    "journey_id",
    "title",
    "activation_conditions",
    "states",
    "transitions",
)


def schema_contract() -> dict[str, Any]:
    return {
        "version": "1",
        "guideline": {
            "required_fields": list(REQUIRED_GUIDELINE_FIELDS),
            "optional_fields": ["journey_id", "state_id", "condition", "action"],
            "scope_values": ["global", "journey_scoped", "state_scoped"],
            "risk_values": ["low", "medium", "high"],
            "duration_values": ["one_off", "persistent", "continuous"],
        },
        "journey": {
            "required_fields": list(REQUIRED_JOURNEY_FIELDS),
            "state_kinds": ["chat_state", "tool_state"],
            "transition_kinds": ["direct", "conditional"],
        },
    }


def validate_guidelines(items: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for i, item in enumerate(items):
        for field in REQUIRED_GUIDELINE_FIELDS:
            if field not in item:
                errors.append(f"guideline[{i}] missing {field}")
        gid = item.get("guideline_id")
        if gid in seen:
            errors.append(f"duplicate guideline_id {gid}")
        seen.add(gid)
    return errors


def validate_journeys(items: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for i, item in enumerate(items):
        for field in REQUIRED_JOURNEY_FIELDS:
            if field not in item:
                errors.append(f"journey[{i}] missing {field}")
        jid = item.get("journey_id")
        if jid in seen:
            errors.append(f"duplicate journey_id {jid}")
        seen.add(jid)
    return errors
