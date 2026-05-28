from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.mcp.schema import pydantic_input_schema
from app.mcp.types import McpToolDefinition, ToolCallResult, ToolContext, ToolHandler
from app.skills.manager import skills_manager


class CallSkillArgs(BaseModel):
    skill_name: str = Field(..., description="Skill name as listed in available skills")


def handle_call_skill(args: dict, ctx: ToolContext) -> ToolCallResult:
    _ = ctx
    parsed = CallSkillArgs.model_validate(args)
    try:
        body = skills_manager.load_body(parsed.skill_name)
    except KeyError:
        return ToolCallResult(
            text=json.dumps({"error": f"unknown skill: {parsed.skill_name}"}, ensure_ascii=False),
            is_error=True,
        )
    payload = {
        "notice": "This is operating instructions, not user-facing content.",
        "skill_name": parsed.skill_name,
        "instructions": body,
    }
    return ToolCallResult(text=json.dumps(payload, ensure_ascii=False))


DEFINITION = McpToolDefinition(
    name="call_skill",
    description="Load a skill's operating instructions (SKILL.md body). Does not execute code.",
    input_schema=pydantic_input_schema(CallSkillArgs),
)
HANDLER: ToolHandler = handle_call_skill
