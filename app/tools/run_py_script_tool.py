from __future__ import annotations

import json
import os
import subprocess
import sys

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.tools.configurable import ids_from_run_manager
from app.workspace.manager import WorkspaceError, manager


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
        user_id, session_id = ids_from_run_manager(run_manager)
        rel = rel_path.strip().replace("\\", "/")
        if not rel.startswith("skills/"):
            return json.dumps(
                {"error": "rel_path must start with skills/"},
                ensure_ascii=False,
            )

        try:
            target = manager.resolve(user_id, session_id, rel)
        except WorkspaceError as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

        if not target.is_file() or target.suffix != ".py":
            return json.dumps(
                {"error": f"not a .py file: {rel_path}"},
                ensure_ascii=False,
            )

        ws = manager.session_dir(user_id, session_id)
        env = {
            **os.environ,
            "SESSION_ID": session_id,
            "USER_ID": user_id,
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
