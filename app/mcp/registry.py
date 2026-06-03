from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any

from langchain_core.tools import BaseTool

from app.mcp.handlers import ALL_HANDLERS
from app.mcp.schema import validate_input_schema
from app.mcp.types import McpToolDefinition, ToolCallResult, ToolContext, ToolHandler
from app.observability.content_store import encode_tool_result, encode_value, preview_text
from app.observability.session_log import append_engine, log_for_context


def _encode_args(log_ctx, arguments: dict[str, Any]) -> dict[str, Any]:
    return {str(k): encode_value(log_ctx, v) for k, v in arguments.items()}


def _normalize_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Drop explicit nulls so handler Pydantic models can apply field defaults."""
    return {k: v for k, v in arguments.items() if v is not None}


def _error_preview(message: str) -> str:
    payload = json.dumps({"ok": False, "error": message}, ensure_ascii=False)
    return preview_text(payload)


def _log_tool_start(log_ctx, name: str, arguments: dict[str, Any]) -> None:
    append_engine(
        log_ctx,
        "tool_start",
        name,
        meta={"args": _encode_args(log_ctx, _normalize_arguments(arguments))},
    )


def _log_tool_end(
    log_ctx,
    name: str,
    result: ToolCallResult,
    *,
    error: str | None = None,
) -> None:
    if error is not None:
        append_engine(
            log_ctx,
            "tool_end",
            name,
            level="ERROR",
            meta={"is_error": True, "preview": _error_preview(error)},
        )
        return
    result_meta = encode_tool_result(log_ctx, result.text)
    result_meta["is_error"] = result.is_error
    if result.is_error and "preview" not in result_meta:
        result_meta["preview"] = preview_text(result.text or _error_preview("tool failed"))
    append_engine(
        log_ctx,
        "tool_end",
        name,
        level="ERROR" if result.is_error else "INFO",
        meta=result_meta,
    )


class ToolRegistry:
    def __init__(self) -> None:
        self._defs: dict[str, McpToolDefinition] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, definition: McpToolDefinition, handler: ToolHandler) -> None:
        validate_input_schema(definition.name, definition.input_schema)
        self._defs[definition.name] = definition
        self._handlers[definition.name] = handler

    def list_definitions(self, *, include_result_set: bool = True) -> list[McpToolDefinition]:
        names = self._ordered_names(include_result_set=include_result_set)
        return [self._defs[n] for n in names]

    def list_tools_public(self, *, include_result_set: bool = True) -> list[dict[str, Any]]:
        return [
            {
                "name": d.name,
                "description": d.description,
                "inputSchema": d.input_schema,
                **({"title": d.title} if d.title else {}),
            }
            for d in self.list_definitions(include_result_set=include_result_set)
        ]

    def summarize_for_prompt(self, *, include_result_set: bool = False) -> str:
        lines = []
        for d in self.list_definitions(include_result_set=include_result_set):
            lines.append(f"- **{d.name}**: {d.description}")
        return "\n".join(lines)

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        ctx: ToolContext,
    ) -> ToolCallResult:
        handler = self._handlers.get(name)
        if handler is None:
            return ToolCallResult(text=json.dumps({"error": f"unknown tool: {name}"}), is_error=True)
        log_ctx = log_for_context(ctx).with_run_id()
        _log_tool_start(log_ctx, name, arguments)
        try:
            result = handler(_normalize_arguments(arguments), ctx)
            if inspect.isawaitable(result):
                result = await result
        except Exception as e:
            _log_tool_end(log_ctx, name, ToolCallResult(text="", is_error=True), error=str(e))
            raise
        _log_tool_end(log_ctx, name, result)
        return result

    def call_tool_sync(
        self,
        name: str,
        arguments: dict[str, Any],
        ctx: ToolContext,
    ) -> ToolCallResult:
        """Run a tool synchronously (tests/CLI). Safe when no event loop is running."""
        handler = self._handlers.get(name)
        if handler is None:
            return ToolCallResult(text=json.dumps({"error": f"unknown tool: {name}"}), is_error=True)
        log_ctx = log_for_context(ctx).with_run_id()
        _log_tool_start(log_ctx, name, arguments)
        try:
            result = handler(_normalize_arguments(arguments), ctx)
            if inspect.isawaitable(result):
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    return asyncio.run(self.call_tool(name, arguments, ctx))
                raise RuntimeError(
                    f"sync tool call for {name!r} cannot await inside a running event loop; "
                    "use await registry.call_tool() instead"
                )
        except Exception as e:
            _log_tool_end(log_ctx, name, ToolCallResult(text="", is_error=True), error=str(e))
            raise
        _log_tool_end(log_ctx, name, result)
        return result

    def to_langchain_tools(self, *, include_result_set: bool = False) -> list[BaseTool]:
        from app.mcp.adapters.langchain import make_langchain_tool

        tools: list[BaseTool] = []
        for name in self._ordered_names(include_result_set=include_result_set):
            tools.append(make_langchain_tool(self, self._defs[name]))
        return tools

    def _ordered_names(self, *, include_result_set: bool) -> list[str]:
        core = [
            "read",
            "write",
            "glob",
            "edit",
            "download",
            "get_current_time",
            "run_py_script",
            "sandbox_exec",
            "daemon_start",
            "daemon_list",
            "daemon_attach",
            "daemon_stop",
            "watch_start",
            "watch_stop",
            "watch_list",
            "call_skill",
            "chroma_in",
            "chroma_out",
        ]
        out = [n for n in core if n in self._defs]
        if include_result_set and "result_set" in self._defs:
            out.append("result_set")
        return out


registry = ToolRegistry()


def _register_handler_module(mod) -> None:
    pairs = getattr(mod, "TOOL_PAIRS", None)
    if pairs:
        for definition, handler in pairs:
            registry.register(definition, handler)
        return
    registry.register(mod.DEFINITION, mod.HANDLER)


for _mod in ALL_HANDLERS:
    _register_handler_module(_mod)
