from __future__ import annotations
import json
from pathlib import Path
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from app.config import settings
class ReadInput(BaseModel):
    rel_path: str = Field(..., description="工作区相对路径（相对会话根目录）")
    offset: int = Field(0, ge=0)
    limit: int = Field(200, ge=1, le=2000)


class ReadTool(BaseTool):
    name: str = "Read"
    description: str = "Read a file from the current session workspace under WORKSPACE_ROOT/<session_id>/."
    args_schema: type[BaseModel] = ReadInput

    def _run(
        self,
        rel_path: str,
        offset: int = 0,
        limit: int = 200,
        *,
        run_manager=None,
        **_: object,
    ) -> str:
        # M5：session 先写死 demo；M7 再从 run_manager / configurable 取 session_id
        session_id = "demo"
        root = Path(settings.workspace_root).resolve()
        ws = (root / session_id).resolve()
        try:
            target = (ws / rel_path).resolve()
        except OSError as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

        try:
            target.relative_to(ws)
        except ValueError:
            return json.dumps(
                {"error": "path escapes workspace"},
                ensure_ascii=False,
            )

        if not target.is_file():
            return json.dumps(
                {"error": f"not a file: {rel_path}"},
                ensure_ascii=False,
            )

        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        chunk = lines[offset : offset + limit]
        out = []
        for i, line in enumerate(chunk, start=offset + 1):
            out.append(f"{i:6d}|{line}")
        return "\n".join(out) if out else "(empty range)"

