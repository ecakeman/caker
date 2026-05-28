from __future__ import annotations

from langchain_core.tools import BaseTool

from app.tools.call_skill_tool import CallSkillTool
from app.tools.read_tool import ReadTool
from app.tools.result_set_tool import ResultSetTool
from app.tools.run_py_script_tool import RunPyScriptTool
from app.tools.chroma_in_tool import ChromaInTool
from app.tools.chroma_out_tool import ChromaOutTool


def build_default_tools(*, include_result_set: bool = False) -> list[BaseTool]:
    tools: list[BaseTool] = [ReadTool(), CallSkillTool(), RunPyScriptTool(), ChromaInTool(), ChromaOutTool()]
    if include_result_set:
        tools.append(ResultSetTool())
    return tools
    