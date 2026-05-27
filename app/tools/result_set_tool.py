from __future__ import annotations

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

class ResultSetInput(BaseModel):
    text: str = Field(...,description="The final answer for the user")

class ResultSetTool(BaseTool):
    name: str = "result_set"
    description: str = "Submit your final answer to the user. Call this last."
    args_schema: type[BaseModel] = ResultSetInput

    def _run(
        self,
        text: str, 
        *, 
        run_manager=None, 
        **_
        ) -> str:
        return text