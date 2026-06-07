from __future__ import annotations

from typing import Any

import parlant.sdk as p

from app.loaders.journey_builder import build_journey
from tools.material_tools import TOOLS


async def install_journeys(
    agent: p.Agent,
    journeys: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, p.Journey]]:
    stats: dict[str, Any] = {"installed": 0, "warnings": [], "tool_states": 0}
    by_id: dict[str, p.Journey] = {}
    for ji, item in enumerate(journeys):
        journey, warnings = await build_journey(agent, item, TOOLS)
        by_id[item["journey_id"]] = journey
        stats["installed"] += 1
        tool_states = sum(1 for s in item.get("states") or [] if s.get("state_kind") == "tool_state")
        stats["tool_states"] += tool_states
        if warnings:
            stats["warnings"].append({"index": ji, "title": item.get("title"), "messages": warnings})
    return stats, by_id
