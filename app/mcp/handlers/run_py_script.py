from __future__ import annotations

import json
import os
import subprocess
import sys

from pydantic import BaseModel, Field

from app.mcp.schema import pydantic_input_schema
from app.mcp.types import McpToolDefinition, ToolCallResult, ToolContext, ToolHandler
from app.workspace import manager as workspace_manager
from app.workspace.manager import WorkspaceError


class RunPyScriptArgs(BaseModel):
    rel_path: str = Field(
        ...,
        description="Path under skills/, must point to a .py file (e.g. skills/demo-hello/scripts/run.py)",
    )
    args: list[str] = Field(default_factory=list)
    timeout_sec: int = Field(60, ge=1, le=600)


def handle_run_py_script(args: dict, ctx: ToolContext) -> ToolCallResult:
    parsed = RunPyScriptArgs.model_validate(args)
    rel = parsed.rel_path.strip().replace("\\", "/")
    if not rel.startswith("skills/"):
        return ToolCallResult(
            text=json.dumps({"error": "rel_path must start with skills/"}),
            is_error=True,
        )
    if "/scripts/" not in rel and not rel.endswith(".py"):
        return ToolCallResult(
            text=json.dumps({"error": "use skills/<name>/scripts/*.py paths"}),
            is_error=True,
        )

    try:
        target = workspace_manager.manager.resolve(ctx.user_id, ctx.session_id, rel)
    except WorkspaceError as e:
        return ToolCallResult(text=json.dumps({"error": str(e)}), is_error=True)

    if not target.is_file() or target.suffix != ".py":
        return ToolCallResult(
            text=json.dumps({"error": f"not a .py file: {parsed.rel_path}"}),
            is_error=True,
        )

    ws = workspace_manager.manager.session_dir(ctx.user_id, ctx.session_id)
    env = {**os.environ, "SESSION_ID": ctx.session_id, "USER_ID": ctx.user_id}
    cmd = [sys.executable, str(target), *parsed.args]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=parsed.timeout_sec,
            cwd=str(ws),
        )
    except subprocess.TimeoutExpired:
        return ToolCallResult(
            text=json.dumps({"error": f"timeout after {parsed.timeout_sec}s"}),
            is_error=True,
        )
    except OSError as e:
        return ToolCallResult(text=json.dumps({"error": str(e)}), is_error=True)

    return ToolCallResult(
        text=json.dumps(
            {
                "exit": proc.returncode,
                "stdout": (proc.stdout or "")[-4000:],
                "stderr": (proc.stderr or "")[-4000:],
            },
            ensure_ascii=False,
        )
    )


DEFINITION = McpToolDefinition(
    name="run_py_script",
    description="Run a Python script from the skills/ tree (skills/<name>/scripts/*.py).",
    input_schema=pydantic_input_schema(RunPyScriptArgs),
)
HANDLER: ToolHandler = handle_run_py_script
