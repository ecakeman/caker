from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.execution.exec_runner import ExecError
from app.execution.exec_pending import describe_attach_target, propose_exec
from app.execution.sandbox_context import session_workspace_host
from app.mcp.schema import pydantic_input_schema
from app.mcp.types import McpToolDefinition, ToolCallResult, ToolContext, ToolHandler


class SandboxExecArgs(BaseModel):
    command: str = Field(..., description="Shell command to run inside the sandbox container")
    cwd: str | None = Field(
        None,
        description="Working directory inside container (default /workspace)",
    )
    timeout_sec: int = Field(120, ge=1, le=600, description="Timeout in seconds")


def handle_sandbox_exec(args: dict, ctx: ToolContext) -> ToolCallResult:
    parsed = SandboxExecArgs.model_validate(args)
    try:
        pending = propose_exec(
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            command=parsed.command,
            cwd=parsed.cwd,
            timeout_sec=parsed.timeout_sec,
        )
        ws = session_workspace_host(ctx.user_id, ctx.session_id)
        attach = describe_attach_target(ctx.user_id, ctx.session_id, ws)
    except ExecError as e:
        return ToolCallResult(
            text=json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
            is_error=True,
        )

    payload = {
        "ok": True,
        "status": "awaiting_user_confirmation",
        "pending_id": pending.pending_id,
        "command": pending.command,
        "cwd": pending.cwd or "/workspace",
        "attach": attach,
        "message": (
            "Command queued for user confirmation in the sandbox UI. "
            "Do not claim it has run until results are available."
        ),
    }
    return ToolCallResult(text=json.dumps(payload, ensure_ascii=False))


DEFINITION = McpToolDefinition(
    name="sandbox_exec",
    description=(
        "Propose running a shell command inside the sandbox Docker environment. "
        "Does not execute until the user confirms in the sandbox UI."
    ),
    input_schema=pydantic_input_schema(SandboxExecArgs),
)
HANDLER: ToolHandler = handle_sandbox_exec
