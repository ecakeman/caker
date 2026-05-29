from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.mcp.schema import pydantic_input_schema
from app.mcp.types import McpToolDefinition, ToolCallResult, ToolContext, ToolHandler
from app.workspace.io import patch_unique
from app.workspace.manager import WorkspaceError


class EditArgs(BaseModel):
    rel_path: str = Field(..., description="Path under data/, outputs/, or compose/")
    old_string: str = Field(..., description="Exact text to replace (must be unique)")
    new_string: str = Field("", description="Replacement text")


def handle_edit(args: dict, ctx: ToolContext) -> ToolCallResult:
    parsed = EditArgs.model_validate(args)
    try:
        result = patch_unique(
            ctx.user_id,
            ctx.session_id,
            parsed.rel_path,
            parsed.old_string,
            parsed.new_string,
        )
    except WorkspaceError as e:
        return ToolCallResult(
            text=json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
            is_error=True,
        )
    return ToolCallResult(
        text=json.dumps({"ok": True, "path": result.rel_path}, ensure_ascii=False)
    )


DEFINITION = McpToolDefinition(
    name="edit",
    description=(
        "Replace a unique string in a writable workspace file (data/, outputs/, or compose/)."
    ),
    input_schema=pydantic_input_schema(EditArgs),
)
HANDLER: ToolHandler = handle_edit
