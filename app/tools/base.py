from __future__ import annotations

from langchain_core.tools import BaseTool

from app.tools.read_tool import ReadTool


def build_default_tools() -> list[BaseTool]:
    return [ReadTool()]