from __future__ import annotations

import re
from typing import Any

_TOOL_PARAM_KEYS = ("topic", "reuse_id", "material_slot_id", "selection_policy")
_STATE_MARKER_PATTERNS = (
    r"customer_facts",
    r"缺参",
    r"已拒绝",
    r"当前状态",
    r"journey_state::",
    r"state_",
    r"profile_",
)
_SEMANTIC_ONLY_RE = re.compile(r"^(客户|用户|当).*(咨询|询问|提到|表示|说)")


def _extract_required_params(tool_actions: list[dict[str, Any]], tools: list[str]) -> list[str]:
    found: set[str] = set()
    for ta in tool_actions:
        if not isinstance(ta, dict):
            continue
        for key in _TOOL_PARAM_KEYS:
            if ta.get(key) not in (None, "", []):
                found.add(key)
        if ta.get("tool"):
            found.add("tool")
    if tools and not found:
        found.add("topic")
    return sorted(found)


def _preferred_scope(item: dict[str, Any]) -> str:
    if item.get("state_id"):
        return "state"
    if item.get("journey_id") or item.get("scope") == "journey_scoped":
        return "journey"
    return "global"


def _condition_markers(condition: str) -> list[str]:
    markers: list[str] = []
    for pat in _STATE_MARKER_PATTERNS:
        if re.search(pat, condition, re.IGNORECASE):
            markers.append(pat.strip("\\").replace("::", "_"))
    if any(k in condition for k in ("返佣", "合规", "监管", "违法")):
        markers.append("high_risk_topic")
    if any(k in condition for k in ("图", "链接", "send_image", "send_link")):
        markers.append("material_request")
    return sorted(set(markers))


def is_condition_deterministic(condition: str, markers: list[str]) -> bool:
    if markers:
        return True
    if "当" in condition and "时" in condition:
        return True
    if _SEMANTIC_ONLY_RE.match(condition.strip()):
        return False
    return len(condition.strip()) >= 12 and not condition.strip().endswith("。")


def enrich_guideline_tool_metadata(guidelines: list[dict[str, Any]]) -> dict[str, Any]:
    """A1: annotate tool-trigger guidelines for governance and matcher projection."""
    tool_count = 0
    nondeterministic: list[str] = []
    for g in guidelines:
        tools = list(g.get("tools") or [])
        tool_actions = list(g.get("tool_actions") or [])
        is_tool = bool(tools or tool_actions)
        markers = _condition_markers(g.get("condition_text") or "")
        deterministic = is_condition_deterministic(g.get("condition_text") or "", markers)
        g["is_tool_trigger"] = is_tool
        g["required_params"] = _extract_required_params(tool_actions, tools)
        g["preferred_scope"] = _preferred_scope(g)
        g["condition_markers"] = markers
        g["condition_deterministic"] = deterministic
        if is_tool:
            tool_count += 1
            if not deterministic:
                nondeterministic.append(str(g.get("guideline_id")))
    return {
        "tool_trigger_count": tool_count,
        "nondeterministic_tool_guidelines": nondeterministic,
        "nondeterministic_tool_count": len(nondeterministic),
    }
