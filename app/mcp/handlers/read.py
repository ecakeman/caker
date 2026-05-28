from __future__ import annotations

from pydantic import BaseModel, Field

from app.mcp.handlers._workspace import resolve_read
from app.mcp.schema import pydantic_input_schema
from app.mcp.types import McpToolDefinition, ToolCallResult, ToolContext, ToolHandler
from app.workspace.manager import WorkspaceError


class ReadArgs(BaseModel):
    rel_path: str = Field(..., description="Path relative to session workspace root")
    offset: int = Field(0, ge=0)
    limit: int = Field(200, ge=1, le=2000)


def handle_read(args: dict, ctx: ToolContext) -> ToolCallResult:
    parsed = ReadArgs.model_validate(args)
    try:
        target = resolve_read(ctx, parsed.rel_path)
    except WorkspaceError as e:
        return ToolCallResult(text=f"<error>{e}</error>", is_error=True)

    if not target.is_file():
        return ToolCallResult(text=f"<error>not a file: {parsed.rel_path}</error>", is_error=True)

    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    chunk = lines[parsed.offset : parsed.offset + parsed.limit]
    out = [f"{i:6d}|{line}" for i, line in enumerate(chunk, start=parsed.offset + 1)]
    return ToolCallResult(text="\n".join(out) if out else "(empty range)")


DEFINITION = McpToolDefinition(
    name="read",
    description="Read a text file from the session workspace (data/, outputs/, or skills/).",
    input_schema=pydantic_input_schema(ReadArgs),
)
HANDLER: ToolHandler = handle_read
