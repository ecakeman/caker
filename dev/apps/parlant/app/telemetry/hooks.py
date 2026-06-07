from __future__ import annotations

from typing import Any

from parlant.core.engines.alpha.engine_context import EngineContext
from parlant.core.engines.alpha.hooks import EngineHookResult, EngineHooks

from app.telemetry.collector import TurnCollector
from app.telemetry.context import get_collector, set_collector


def _draft_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        return str(payload.get("message") or payload.get("content") or "")
    return str(payload or "")


async def on_acknowledged(context: EngineContext, _payload: Any, _exc: Exception | None) -> EngineHookResult:
    collector = get_collector()
    if collector is None:
        return EngineHookResult.CALL_NEXT
    collector.bind_context(context)
    collector.start_stage("context_build")
    return EngineHookResult.CALL_NEXT


async def on_preparing(context: EngineContext, _payload: Any, _exc: Exception | None) -> EngineHookResult:
    collector = get_collector()
    if collector is None:
        return EngineHookResult.CALL_NEXT
    collector.stop_stage("context_build")
    collector.start_stage("arq_enforcement")
    return EngineHookResult.CALL_NEXT


async def on_preparation_iteration_end(
    context: EngineContext, _payload: Any, _exc: Exception | None
) -> EngineHookResult:
    collector = get_collector()
    if collector is None:
        return EngineHookResult.CALL_NEXT
    collector.sync_tools_from_context(context)
    if context.state.iterations:
        iteration = context.state.iterations[-1]
        collector.note_executed_tools(list(getattr(iteration, "executed_tools", []) or []))
    return EngineHookResult.CALL_NEXT


async def on_generating_messages(
    context: EngineContext, _payload: Any, _exc: Exception | None
) -> EngineHookResult:
    collector = get_collector()
    if collector is None:
        return EngineHookResult.CALL_NEXT
    collector.stop_stage("arq_enforcement")
    collector.start_stage("compose")
    return EngineHookResult.CALL_NEXT


async def on_draft_generated(context: EngineContext, payload: Any, _exc: Exception | None) -> EngineHookResult:
    collector = get_collector()
    if collector is None:
        return EngineHookResult.CALL_NEXT
    collector.set_agent_response(_draft_text(payload))
    return EngineHookResult.CALL_NEXT


async def on_message_generated(context: EngineContext, payload: Any, _exc: Exception | None) -> EngineHookResult:
    collector = get_collector()
    if collector is None:
        return EngineHookResult.CALL_NEXT
    collector.set_agent_response(_draft_text(payload))
    return EngineHookResult.CALL_NEXT


async def on_messages_emitted(context: EngineContext, _payload: Any, _exc: Exception | None) -> EngineHookResult:
    collector = get_collector()
    if collector is None:
        return EngineHookResult.CALL_NEXT
    collector.stop_stage("compose")
    collector.start_stage("writeback")
    collector.stop_stage("writeback")
    collector.finalize(context)
    set_collector(None)
    return EngineHookResult.CALL_NEXT


def begin_turn_collector(collector: TurnCollector) -> None:
    set_collector(collector)
    collector.start_stage("context_build")


def register_telemetry_hooks(hooks: EngineHooks) -> EngineHooks:
    hooks.on_acknowledged.append(on_acknowledged)
    hooks.on_preparing.append(on_preparing)
    hooks.on_preparation_iteration_end.append(on_preparation_iteration_end)
    hooks.on_generating_messages.append(on_generating_messages)
    hooks.on_draft_generated.append(on_draft_generated)
    hooks.on_message_generated.append(on_message_generated)
    hooks.on_messages_emitted.append(on_messages_emitted)
    return hooks
