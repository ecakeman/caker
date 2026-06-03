from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.execution.file_watch import list_watches, start_watch, stop_watch
from app.mcp.schema import pydantic_input_schema
from app.mcp.types import McpToolDefinition, ToolCallResult, ToolContext, ToolHandler
from app.workspace.manager import WorkspaceError


class WatchStartArgs(BaseModel):
    paths: list[str] = Field(..., min_length=1, description="Workspace-relative file paths to watch")
    poll_interval_sec: float | None = Field(
        None,
        ge=0.5,
        le=60,
        description="Poll interval in seconds (default from settings, typically 1)",
    )


class WatchStopArgs(BaseModel):
    watch_id: str = Field(..., description="watch_id returned by watch_start")


def handle_watch_start(args: dict, ctx: ToolContext) -> ToolCallResult:
    parsed = WatchStartArgs.model_validate(args)
    try:
        payload = start_watch(
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            paths=parsed.paths,
            poll_interval_sec=parsed.poll_interval_sec,
        )
    except WorkspaceError as e:
        return ToolCallResult(
            text=json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
            is_error=True,
        )
    return ToolCallResult(text=json.dumps(payload, ensure_ascii=False))


def handle_watch_stop(args: dict, ctx: ToolContext) -> ToolCallResult:
    parsed = WatchStopArgs.model_validate(args)
    try:
        payload = stop_watch(
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            watch_id=parsed.watch_id,
        )
    except WorkspaceError as e:
        return ToolCallResult(
            text=json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
            is_error=True,
        )
    return ToolCallResult(text=json.dumps(payload, ensure_ascii=False))


def handle_watch_list(args: dict, ctx: ToolContext) -> ToolCallResult:
    payload = list_watches(user_id=ctx.user_id, session_id=ctx.session_id)
    return ToolCallResult(text=json.dumps(payload, ensure_ascii=False))


DEFINITION_START = McpToolDefinition(
    name="watch_start",
    description=(
        "Start polling file changes under the session workspace. "
        "Events append to logs/watch_events.jsonl; read that file for alerts."
    ),
    input_schema=pydantic_input_schema(WatchStartArgs),
)
HANDLER_START: ToolHandler = handle_watch_start

DEFINITION_STOP = McpToolDefinition(
    name="watch_stop",
    description="Stop a file watch started with watch_start.",
    input_schema=pydantic_input_schema(WatchStopArgs),
)
HANDLER_STOP: ToolHandler = handle_watch_stop

DEFINITION_LIST = McpToolDefinition(
    name="watch_list",
    description="List active file watches in this session.",
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
)
HANDLER_LIST: ToolHandler = handle_watch_list

TOOL_PAIRS = [
    (DEFINITION_START, HANDLER_START),
    (DEFINITION_STOP, HANDLER_STOP),
    (DEFINITION_LIST, HANDLER_LIST),
]
