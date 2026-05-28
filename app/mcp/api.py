from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.mcp.registry import registry
from app.mcp.types import ToolContext

router = APIRouter(prefix="/mcp", tags=["mcp"])


class ToolCallIn(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    user_id: str = "local"
    session_id: str = "demo"


@router.get("/tools")
async def list_tools() -> dict:
    return {"tools": registry.list_tools_public(include_result_set=True)}


@router.post("/tools/call")
async def call_tool(body: ToolCallIn) -> dict:
    ctx = ToolContext(user_id=body.user_id.strip() or "local", session_id=body.session_id.strip() or "demo")
    result = await registry.call_tool(body.name, body.arguments, ctx)
    return {
        "content": result.to_mcp_content(),
        "isError": result.is_error,
    }
