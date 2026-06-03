from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.execution.exec_runner import ExecError
from app.execution.daemon import attach_daemon, list_daemons, start_daemon, stop_daemon
from app.mcp.schema import pydantic_input_schema
from app.mcp.types import McpToolDefinition, ToolCallResult, ToolContext, ToolHandler


class DaemonStartArgs(BaseModel):
    name: str = Field(..., description="Unique daemon name (letters, digits, _ and -)")
    command: str = Field(..., description="Shell command to run in background inside sandbox container")


class DaemonAttachArgs(BaseModel):
    name: str = Field(..., description="Registered daemon name")
    tail_lines: int = Field(200, ge=1, le=2000, description="Lines of recent output to return")


class DaemonStopArgs(BaseModel):
    name: str = Field(..., description="Registered daemon name to stop")


def _err(e: Exception) -> ToolCallResult:
    return ToolCallResult(
        text=json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
        is_error=True,
    )


def handle_daemon_start(args: dict, ctx: ToolContext) -> ToolCallResult:
    parsed = DaemonStartArgs.model_validate(args)
    try:
        payload = start_daemon(
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            name=parsed.name,
            command=parsed.command,
        )
    except ExecError as e:
        return _err(e)
    return ToolCallResult(text=json.dumps(payload, ensure_ascii=False))


def handle_daemon_list(args: dict, ctx: ToolContext) -> ToolCallResult:
    try:
        payload = list_daemons(user_id=ctx.user_id, session_id=ctx.session_id)
    except ExecError as e:
        return _err(e)
    return ToolCallResult(text=json.dumps(payload, ensure_ascii=False))


def handle_daemon_attach(args: dict, ctx: ToolContext) -> ToolCallResult:
    parsed = DaemonAttachArgs.model_validate(args)
    try:
        payload = attach_daemon(
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            name=parsed.name,
            tail_lines=parsed.tail_lines,
        )
    except ExecError as e:
        return _err(e)
    return ToolCallResult(text=json.dumps(payload, ensure_ascii=False))


def handle_daemon_stop(args: dict, ctx: ToolContext) -> ToolCallResult:
    parsed = DaemonStopArgs.model_validate(args)
    try:
        payload = stop_daemon(
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            name=parsed.name,
        )
    except ExecError as e:
        return _err(e)
    return ToolCallResult(text=json.dumps(payload, ensure_ascii=False))


DEFINITION_START = McpToolDefinition(
    name="daemon_start",
    description=(
        "Start a long-running shell command in the sandbox container background "
        "(tmux session or nohup). Returns immediately; logs go to logs/daemons/<name>.log."
    ),
    input_schema=pydantic_input_schema(DaemonStartArgs),
)
HANDLER_START: ToolHandler = handle_daemon_start

DEFINITION_LIST = McpToolDefinition(
    name="daemon_list",
    description="List background daemons for this session and their running/exited status.",
    input_schema={"type": "object", "properties": {}, "additionalProperties": False},
)
HANDLER_LIST: ToolHandler = handle_daemon_list

DEFINITION_ATTACH = McpToolDefinition(
    name="daemon_attach",
    description="Fetch recent stdout/stderr from a background daemon (like attach_session).",
    input_schema=pydantic_input_schema(DaemonAttachArgs),
)
HANDLER_ATTACH: ToolHandler = handle_daemon_attach

DEFINITION_STOP = McpToolDefinition(
    name="daemon_stop",
    description="Stop a background daemon started with daemon_start.",
    input_schema=pydantic_input_schema(DaemonStopArgs),
)
HANDLER_STOP: ToolHandler = handle_daemon_stop

TOOL_PAIRS = [
    (DEFINITION_START, HANDLER_START),
    (DEFINITION_LIST, HANDLER_LIST),
    (DEFINITION_ATTACH, HANDLER_ATTACH),
    (DEFINITION_STOP, HANDLER_STOP),
]
