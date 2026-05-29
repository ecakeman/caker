from __future__ import annotations

import fnmatch
import json

from pydantic import BaseModel, Field

from app.mcp.schema import pydantic_input_schema
from app.mcp.types import McpToolDefinition, ToolCallResult, ToolContext, ToolHandler
from app.workspace import manager as workspace_manager
from app.workspace.manager import WorkspaceError
from app.workspace.paths import normalize_glob_pattern


class GlobArgs(BaseModel):
    pattern: str = Field(..., description="Glob pattern relative to session root, e.g. data/**/*.txt")
    max_results: int = Field(100, ge=1, le=500)


def handle_glob(args: dict, ctx: ToolContext) -> ToolCallResult:
    parsed = GlobArgs.model_validate(args)
    try:
        pattern = normalize_glob_pattern(parsed.pattern)
        ws = workspace_manager.manager.session_dir(ctx.user_id, ctx.session_id)
    except WorkspaceError as e:
        return ToolCallResult(
            text=json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
            is_error=True,
        )

    matches: list[str] = []
    for p in sorted(ws.rglob("*")):
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(ws).as_posix()
        except ValueError:
            continue
        if not fnmatch.fnmatch(rel, pattern):
            continue
        matches.append(rel)
        if len(matches) >= parsed.max_results:
            break

    return ToolCallResult(
        text=json.dumps({"ok": True, "count": len(matches), "paths": matches}, ensure_ascii=False)
    )


DEFINITION = McpToolDefinition(
    name="glob",
    description="List files in the session workspace matching a glob pattern.",
    input_schema=pydantic_input_schema(GlobArgs),
)
HANDLER: ToolHandler = handle_glob
