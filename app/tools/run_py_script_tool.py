from __future__ import annotations

import json
import os
import subprocess
import sys

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.workspace.manager import WorkspaceError, manager


def _session_id_from_run_manager(run_manager) -> str:
    if run_manager is None:
        return "demo"
    cfg = getattr(run_manager, "config", None) or {}
    if not isinstance(cfg, dict):
        return "demo"
    configurable = cfg.get("configurable") or {}
    if not isinstance(configurable, dict):
        return "demo"
    return str(configurable.get("session_id") or "demo")


class RunPyInput(BaseModel):
    rel_path: str = Field(..., description="路径必须以 skills/ 开头")
    args: list[str] = Field(default_factory=list)
    timeout_sec: int = Field(60, ge=1, le=600)


class RunPyScriptTool(BaseTool):
    name: str = "RunPyScript"
    description: str = (
        "Run a Python script under the session workspace skills/. "
        "Returns exit code, stdout, stderr as JSON."
    )
    args_schema: type[BaseModel] = RunPyInput

    def _run(
        self,
        rel_path: str,
        args: list[str] | None = None,
        timeout_sec: int = 60,
        *,
        run_manager=None,
        **_: object,
    ) -> str:
        session_id = _session_id_from_run_manager(run_manager)
        rel = rel_path.strip().replace("\\", "/")
        if not rel.startswith("skills/"):
            return json.dumps(
                {"error": "rel_path must start with skills/"},
                ensure_ascii=False,
            )

        try:
            target = manager.resolve(session_id, rel)
        except WorkspaceError as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

        if not target.is_file() or target.suffix != ".py":
            return json.dumps(
                {"error": f"not a .py file: {rel_path}"},
                ensure_ascii=False,
            )

        ws = manager.session_dir(session_id)
        env = {
            **os.environ,
            "SESSION_ID": session_id,
            "USER_ID": "local",
        }
        cmd = [sys.executable, str(target), *(args or [])]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout_sec,
                cwd=str(ws),
            )
        except subprocess.TimeoutExpired:
            return json.dumps(
                {"error": f"timeout after {timeout_sec}s", "rel_path": rel},
                ensure_ascii=False,
            )
        except OSError as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

        return json.dumps(
            {
                "exit": proc.returncode,
                "stdout": (proc.stdout or "")[-4000:],
                "stderr": (proc.stderr or "")[-4000:],
            },
            ensure_ascii=False,
        )