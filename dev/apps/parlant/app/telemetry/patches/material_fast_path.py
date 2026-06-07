"""Skip extra guideline rematching after metadata-only material tools (broker parity)."""

from __future__ import annotations

import logging
import os
from typing import Any

from parlant.core.engines.alpha.engine import AlphaEngine

from app.telemetry.context import get_collector

_logger = logging.getLogger(__name__)
_PATCH_APPLIED = False
_ORIGINAL_CHECK_IF_PREPARED: Any = None


def _truthy(name: str, default: str = "1") -> bool:
    raw = os.environ.get(name)
    if raw is None and name.startswith("PARLANT_"):
        raw = os.environ.get(name.replace("PARLANT_", "BROKER_", 1))
    return (raw or default).strip().lower() in {"1", "true", "yes", "on"}


def _material_tool_names() -> set[str]:
    raw = (
        os.environ.get("PARLANT_MATERIAL_FAST_PATH_TOOLS")
        or os.environ.get("BROKER_MATERIAL_FAST_PATH_TOOLS")
        or "send_image,send_link,send_quoted_chat,send_shareuser"
    )
    return {part.strip() for part in raw.split(",") if part.strip()}


def _tool_name(tool_id: Any) -> str:
    if name := getattr(tool_id, "tool_name", None):
        return str(name)
    raw = str(tool_id)
    return raw.split(":", 1)[1] if ":" in raw else raw


def _has_tool_parameter_problem(tool_insights: Any) -> bool:
    return bool(
        getattr(tool_insights, "missing_data", None)
        or getattr(tool_insights, "invalid_data", None)
    )


def _is_material_only_result(result: Any) -> tuple[bool, list[str]]:
    executed_tools = list(getattr(getattr(result, "state", None), "executed_tools", []) or [])
    if not executed_tools:
        return False, []
    tool_names = [_tool_name(tool_id) for tool_id in executed_tools]
    material_tools = _material_tool_names()
    return all(name in material_tools for name in tool_names), tool_names


async def _patched_check_if_prepared(
    self: AlphaEngine,
    context: Any,
    result: Any,
    plan: Any,
) -> bool:
    if not _truthy("PARLANT_MATERIAL_TOOL_FAST_PATH", "1"):
        return await _ORIGINAL_CHECK_IF_PREPARED(self, context, result, plan)

    is_material_only, tool_names = _is_material_only_result(result)
    if (
        is_material_only
        and not getattr(plan, "needs_additional_iteration", False)
        and not _has_tool_parameter_problem(getattr(getattr(result, "state", None), "tool_insights", None))
    ):
        collector = get_collector()
        if collector is not None:
            collector.note_material_fast_path(tool_names)
        return True

    return await _ORIGINAL_CHECK_IF_PREPARED(self, context, result, plan)


def apply_material_fast_path_patch() -> None:
    global _PATCH_APPLIED, _ORIGINAL_CHECK_IF_PREPARED
    if _PATCH_APPLIED:
        return
    _ORIGINAL_CHECK_IF_PREPARED = AlphaEngine._check_if_prepared
    AlphaEngine._check_if_prepared = _patched_check_if_prepared  # type: ignore[method-assign]
    _PATCH_APPLIED = True
    _logger.info(
        "telemetry: material_tool_fast_path enabled=%s tools=%s",
        _truthy("PARLANT_MATERIAL_TOOL_FAST_PATH", "1"),
        ",".join(sorted(_material_tool_names())),
    )
