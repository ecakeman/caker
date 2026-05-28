from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, create_model

from app.mcp.context import context_from_runnable_config
from typing import TYPE_CHECKING

from app.mcp.types import McpToolDefinition

if TYPE_CHECKING:
    from app.mcp.registry import ToolRegistry


def _args_model_from_schema(definition: McpToolDefinition) -> type[BaseModel]:
    props = definition.input_schema.get("properties") or {}
    required = set(definition.input_schema.get("required") or [])
    fields: dict[str, Any] = {}
    for key, spec in props.items():
        py_type: Any = Any
        t = spec.get("type")
        if t == "integer":
            py_type = int
        elif t == "number":
            py_type = float
        elif t == "boolean":
            py_type = bool
        elif t == "array":
            py_type = list
        elif t == "string":
            py_type = str
        default = ... if key in required else None
        desc = spec.get("description")
        if desc:
            fields[key] = (py_type, Field(default, description=desc) if default is not ... else Field(description=desc))
        else:
            fields[key] = (py_type, default)
    if not fields:
        return create_model(f"{definition.name}_Args")
    return create_model(f"{definition.name}_Args", **fields)


def make_langchain_tool(registry: "ToolRegistry", definition: McpToolDefinition) -> BaseTool:
    schema_cls = _args_model_from_schema(definition)
    tool_name = definition.name
    tool_desc = definition.description

    class _AdapterTool(BaseTool):
        name: str = tool_name
        description: str = tool_desc
        args_schema: type[BaseModel] = schema_cls

        def _run(
            self,
            *,
            run_manager=None,
            config: RunnableConfig | None = None,
            **kwargs: Any,
        ) -> str:
            ctx = context_from_runnable_config(config)
            result = registry.call_tool_sync(tool_name, kwargs, ctx)
            return result.text

    return _AdapterTool()
