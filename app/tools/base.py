from __future__ import annotations

from langchain_core.tools import BaseTool

from app.tools.call_skill_tool import CallSkillTool
from app.tools.read_tool import ReadTool
from app.tools.run_py_script_tool import RunPyScriptTool


def build_default_tools() -> list[BaseTool]:
    return [ReadTool(), CallSkillTool(), RunPyScriptTool()]