from __future__ import annotations

from typing import Any

import parlant.sdk as p

from tools.material_tools import TOOLS


async def install_guidelines(
    agent: p.Agent,
    guidelines: list[dict[str, Any]],
    scope_map: dict[str, Any],
    journeys_by_id: dict[str, p.Journey],
) -> dict[str, int]:
    stats = {"global": 0, "journey_scoped": 0, "with_tools": 0}
    journey_scoped_ids: set[str] = set()
    for ids in (scope_map.get("journey_scoped") or {}).values():
        journey_scoped_ids.update(ids)
    for ids in (scope_map.get("state_scoped") or {}).values():
        journey_scoped_ids.update(ids)

    for item in guidelines:
        gid = item["guideline_id"]
        tool_refs = [TOOLS[t] for t in item.get("tools") or [] if t in TOOLS]
        kwargs: dict[str, Any] = {
            "condition": item["condition_text"],
            "action": item["action_text"],
            "track": False,
        }
        if tool_refs:
            kwargs["tools"] = tool_refs
            stats["with_tools"] += 1
        if gid in journey_scoped_ids and item.get("journey_id") in journeys_by_id:
            await journeys_by_id[item["journey_id"]].create_guideline(**kwargs)
            stats["journey_scoped"] += 1
        else:
            await agent.create_guideline(**kwargs)
            stats["global"] += 1
    stats["installed"] = stats["global"] + stats["journey_scoped"]
    return stats
