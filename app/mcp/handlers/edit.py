from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.mcp.handlers._workspace import resolve_write
from app.mcp.schema import pydantic_input_schema
from app.mcp.types import McpToolDefinition, ToolCallResult, ToolContext, ToolHandler
from app.workspace.manager import WorkspaceError


class EditArgs(BaseModel):
    rel_path: str = Field(..., description="Path under data/ or outputs/")
    old_string: str = Field(..., description="Exact text to replace (must be unique)")
    new_string: str = Field("", description="Replacement text")


def handle_edit(args: dict, ctx: ToolContext) -> ToolCallResult:
    parsed = EditArgs.model_validate(args)
    try:
        target = resolve_write(ctx, parsed.rel_path)
    except WorkspaceError as e:
        return ToolCallResult(text=json.dumps({"ok": False, "error": str(e)}), is_error=True)

    if not target.is_file():
        return ToolCallResult(
            text=json.dumps({"ok": False, "error": f"not a file: {parsed.rel_path}"}),
            is_error=True,
        )

    text = target.read_text(encoding="utf-8", errors="replace")
    count = text.count(parsed.old_string)
    if count == 0:
        return ToolCallResult(
            text=json.dumps({"ok": False, "error": "old_string not found"}),
            is_error=True,
        )
    if count > 1:
        return ToolCallResult(
            text=json.dumps({"ok": False, "error": f"old_string not unique ({count} matches)"}),
            is_error=True,
        )

    target.write_text(text.replace(parsed.old_string, parsed.new_string, 1), encoding="utf-8")
    return ToolCallResult(text=json.dumps({"ok": True, "path": parsed.rel_path}, ensure_ascii=False))


DEFINITION = McpToolDefinition(
    name="edit",
    description="Replace a unique string in a writable workspace file (data/ or outputs/).",
    input_schema=pydantic_input_schema(EditArgs),
)
HANDLER: ToolHandler = handle_edit
