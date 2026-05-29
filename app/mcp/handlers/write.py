from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.mcp.schema import pydantic_input_schema
from app.mcp.types import McpToolDefinition, ToolCallResult, ToolContext, ToolHandler
from app.workspace.io import write_text_file
from app.workspace.manager import WorkspaceError


class WriteArgs(BaseModel):
    rel_path: str = Field(..., description="Path under data/, outputs/, or compose/")
    content: str = Field(..., description="Full file content to write")
    encoding: str = Field("utf-8", description="Text encoding")


def handle_write(args: dict, ctx: ToolContext) -> ToolCallResult:
    parsed = WriteArgs.model_validate(args)
    try:
        result = write_text_file(
            ctx.user_id,
            ctx.session_id,
            parsed.rel_path,
            parsed.content,
            encoding=parsed.encoding,
        )
    except WorkspaceError as e:
        return ToolCallResult(
            text=json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
            is_error=True,
        )
    return ToolCallResult(
        text=json.dumps(
            {"ok": True, "path": result.rel_path, "bytes": result.bytes_written},
            ensure_ascii=False,
        )
    )


DEFINITION = McpToolDefinition(
    name="write",
    description=(
        "Create or overwrite a file under data/, outputs/, or compose/ in the session workspace."
    ),
    input_schema=pydantic_input_schema(WriteArgs),
)
HANDLER: ToolHandler = handle_write
