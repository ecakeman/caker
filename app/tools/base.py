from __future__ import annotations

from langchain_core.tools import BaseTool

from app.mcp.registry import registry


def build_default_tools(*, include_result_set: bool = False) -> list[BaseTool]:
    return registry.to_langchain_tools(include_result_set=include_result_set)
