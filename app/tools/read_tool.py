from __future__ import annotations

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.tools.configurable import ids_from_run_manager
from app.workspace.manager import WorkspaceError, manager


class ReadInput(BaseModel):
    rel_path: str = Field(..., description="工作区相对路径（相对会话根目录）")
    offset: int = Field(0, ge=0)
    limit: int = Field(200, ge=1, le=2000)


class ReadTool(BaseTool):
    name: str = "Read"
    description: str = (
        "Read a file from the current session workspace under "
        "WORKSPACE_ROOT/<user_id>/<session_id>/."
    )
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
        user_id, session_id = ids_from_run_manager(run_manager)
        try:
            target = manager.resolve(user_id, session_id, rel_path)
        except WorkspaceError as e:
            return f"<error>{e}</error>"

        if not target.is_file():
            return f"<error>not a file: {rel_path}</error>"

        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        chunk = lines[offset : offset + limit]
        out = []
        for i, line in enumerate(chunk, start=offset + 1):
            out.append(f"{i:6d}|{line}")
        return "\n".join(out) if out else "(empty range)"
