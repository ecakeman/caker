from __future__ import annotations

import json
import uuid

from pydantic import BaseModel, Field

from app.mcp.schema import pydantic_input_schema
from app.mcp.types import McpToolDefinition, ToolCallResult, ToolContext, ToolHandler
from app.mempalace.chroma_store import add


class ChromaInArgs(BaseModel):
    text: str = Field(..., description="Information to store in long-term vector memory for this user")


def handle_chroma_in(args: dict, ctx: ToolContext) -> ToolCallResult:
    parsed = ChromaInArgs.model_validate(args)
    memory_id = uuid.uuid4().hex
    metadata = {
        "user_id": ctx.user_id,
        "session_id": ctx.session_id,
    }
    try:
        add(memory_id, parsed.text, metadata)
    except Exception as e:
        return ToolCallResult(
            text=json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
            is_error=True,
        )
    return ToolCallResult(
        text=json.dumps(
            {"ok": True, "memory_id": memory_id, "metadata": metadata},
            ensure_ascii=False,
        )
    )


DEFINITION = McpToolDefinition(
    name="chroma_in",
    description=(
        "Stores text in the user's long-term vector memory (Chroma). "
        "Use when the user explicitly asks to remember something for later sessions."
    ),
    input_schema=pydantic_input_schema(ChromaInArgs),
)
HANDLER: ToolHandler = handle_chroma_in
