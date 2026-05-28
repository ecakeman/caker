from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.mcp.handlers._workspace import resolve_write
from app.mcp.schema import pydantic_input_schema
from app.mcp.types import McpToolDefinition, ToolCallResult, ToolContext, ToolHandler
from app.workspace.manager import WorkspaceError


class WriteArgs(BaseModel):
    rel_path: str = Field(..., description="Path under data/ or outputs/")
    content: str = Field(..., description="Full file content to write")
    encoding: str = Field("utf-8", description="Text encoding")


def handle_write(args: dict, ctx: ToolContext) -> ToolCallResult:
    parsed = WriteArgs.model_validate(args)
    try:
        target = resolve_write(ctx, parsed.rel_path)
    except WorkspaceError as e:
        return ToolCallResult(text=json.dumps({"ok": False, "error": str(e)}), is_error=True)

    target.parent.mkdir(parents=True, exist_ok=True)
    data = parsed.content.encode(parsed.encoding)
    target.write_bytes(data)
    return ToolCallResult(
        text=json.dumps(
            {"ok": True, "path": parsed.rel_path, "bytes": len(data)},
            ensure_ascii=False,
        )
    )


DEFINITION = McpToolDefinition(
    name="write",
    description="Create or overwrite a file under data/ or outputs/ in the session workspace.",
    input_schema=pydantic_input_schema(WriteArgs),
)
HANDLER: ToolHandler = handle_write
