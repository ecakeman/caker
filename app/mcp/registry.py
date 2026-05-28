from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any

from langchain_core.tools import BaseTool

from app.mcp.handlers import ALL_HANDLERS
from app.mcp.schema import validate_input_schema
from app.mcp.types import McpToolDefinition, ToolCallResult, ToolContext, ToolHandler


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
        result = handler(arguments, ctx)
        if inspect.isawaitable(result):
            result = await result
        return result

    def call_tool_sync(
        self,
        name: str,
        arguments: dict[str, Any],
        ctx: ToolContext,
    ) -> ToolCallResult:
        return asyncio.run(self.call_tool(name, arguments, ctx))

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
            "call_skill",
            "chroma_in",
            "chroma_out",
        ]
        out = [n for n in core if n in self._defs]
        if include_result_set and "result_set" in self._defs:
            out.append("result_set")
        return out


registry = ToolRegistry()

for _mod in ALL_HANDLERS:
    registry.register(_mod.DEFINITION, _mod.HANDLER)
