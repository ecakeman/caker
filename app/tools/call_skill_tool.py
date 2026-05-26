from __future__ import annotations

import json

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.skills.manager import skills_manager

class CallSkillInput(BaseModel):
    skill_name: str=Field(
        ...,
        description="Skill name as listed in available skills",
    )

class CallSkillTool(BaseTool):
    name: str = "call_skill"
    description: str = "Load a skill's operating instructions. NOT a runner."
    args_schema: type[BaseModel] = CallSkillInput

    def _run(
        self,
        skill_name: str,
        *,
        run_manager=None,
        **_:object
    ) -> str:
        try:
            body = skills_manager.load_body(skill_name)
        except KeyError:
            return json.dumps(
                {"error": f"unknown skill: {skill_name}"},
                ensure_ascii=False,
            )
        payload = {
            "notice": "This is operating instructions, not user-facing content.",
            "skill_name": skill_name,
            "instructions": body,
        }
        return json.dumps(payload, ensure_ascii=False)