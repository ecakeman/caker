from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.mcp.schema import pydantic_input_schema
from app.mcp.types import McpToolDefinition, ToolCallResult, ToolContext, ToolHandler
from app.mempalace.chroma_store import search


class ChromaOutArgs(BaseModel):
    text: str = Field(..., description="Query text to search long-term vector memory for this user")


def handle_chroma_out(args: dict, ctx: ToolContext) -> ToolCallResult:
    parsed = ChromaOutArgs.model_validate(args)
    try:
        hits = search(parsed.text, k=3, where={"user_id": ctx.user_id})
        items = [
            {"id": memory_id, "text": doc, "metadata": metadata}
            for memory_id, doc, metadata in hits
        ]
        return ToolCallResult(
            text=json.dumps({"ok": True, "count": len(items), "hits": items}, ensure_ascii=False)
        )
    except Exception as e:
        return ToolCallResult(
            text=json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
            is_error=True,
        )


DEFINITION = McpToolDefinition(
    name="chroma_out",
    description=(
        "Searches the user's long-term vector memory (Chroma) by semantic similarity. "
        "Use when the user asks to recall something they asked to remember earlier."
    ),
    input_schema=pydantic_input_schema(ChromaOutArgs),
)
HANDLER: ToolHandler = handle_chroma_out
