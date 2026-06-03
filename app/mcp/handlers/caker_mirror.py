from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.mcp.schema import pydantic_input_schema
from app.mcp.types import McpToolDefinition, ToolCallResult, ToolContext, ToolHandler
from app.mirror.github import MirrorError, mirror_glob, mirror_read


class MirrorReadArgs(BaseModel):
    rel_path: str = Field(
        ...,
        description="Path relative to Caker repo root on GitHub, e.g. app/main.py or system_prompt.md",
    )
    offset: int = Field(
        0,
        description="0-based line offset; negative counts from end (e.g. -50 for last 50 lines)",
    )
    limit: int = Field(200, ge=1, le=2000)


class MirrorGlobArgs(BaseModel):
    pattern: str = Field(..., description="Glob pattern relative to repo root, e.g. app/mcp/**/*.py")
    max_results: int = Field(100, ge=1, le=500)


def _err(message: str) -> ToolCallResult:
    return ToolCallResult(
        text=json.dumps({"ok": False, "error": message}, ensure_ascii=False),
        is_error=True,
    )


def handle_caker_mirror_read(args: dict, ctx: ToolContext) -> ToolCallResult:
    parsed = MirrorReadArgs.model_validate(args)
    try:
        result = mirror_read(parsed.rel_path, offset=parsed.offset, limit=parsed.limit)
    except MirrorError as e:
        return _err(str(e))
    return ToolCallResult(text=result.text)


def handle_caker_mirror_glob(args: dict, ctx: ToolContext) -> ToolCallResult:
    parsed = MirrorGlobArgs.model_validate(args)
    try:
        payload = mirror_glob(parsed.pattern, max_results=parsed.max_results)
    except MirrorError as e:
        return _err(str(e))
    return ToolCallResult(text=json.dumps(payload, ensure_ascii=False))


DEFINITION_READ = McpToolDefinition(
    name="caker_mirror_read",
    description=(
        "Read a text file from the published Caker source mirror on GitHub "
        "(https://github.com/ecakeman/caker). Read-only; cannot modify Caker itself. "
        "Use when explaining how Caker tools, runtime, or UI work."
    ),
    input_schema=pydantic_input_schema(MirrorReadArgs),
)
HANDLER_READ: ToolHandler = handle_caker_mirror_read

DEFINITION_GLOB = McpToolDefinition(
    name="caker_mirror_glob",
    description=(
        "List file paths in the Caker GitHub mirror matching a glob. "
        "Read-only introspection of the Caker codebase."
    ),
    input_schema=pydantic_input_schema(MirrorGlobArgs),
)
HANDLER_GLOB: ToolHandler = handle_caker_mirror_glob

TOOL_PAIRS = [
    (DEFINITION_READ, HANDLER_READ),
    (DEFINITION_GLOB, HANDLER_GLOB),
]
