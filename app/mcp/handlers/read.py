from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.mcp.schema import pydantic_input_schema
from app.mcp.types import McpToolDefinition, ToolCallResult, ToolContext, ToolHandler
from app.workspace.io import read_text_file
from app.workspace.manager import WorkspaceError


class ReadArgs(BaseModel):
    rel_path: str = Field(..., description="Path relative to session workspace root")
    offset: int = Field(
        0,
        description="0-based line offset; negative values count from end (e.g. -50 = start 50 lines from EOF)",
    )
    limit: int = Field(200, ge=1, le=2000)


def handle_read(args: dict, ctx: ToolContext) -> ToolCallResult:
    parsed = ReadArgs.model_validate(args)
    try:
        result = read_text_file(
            ctx.user_id,
            ctx.session_id,
            parsed.rel_path,
            offset=parsed.offset,
            limit=parsed.limit,
        )
    except WorkspaceError as e:
        return ToolCallResult(
            text=json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
            is_error=True,
        )
    return ToolCallResult(text=result.text)


DEFINITION = McpToolDefinition(
    name="read",
    description=(
        "Read a text file from the session workspace (data/, outputs/, compose/, logs/, or skills/). "
        "Use offset=-N to read from the end (e.g. offset=-50, limit=50 for the last 50 lines)."
    ),
    input_schema=pydantic_input_schema(ReadArgs),
)
HANDLER: ToolHandler = handle_read
