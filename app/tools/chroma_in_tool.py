from __future__ import annotations

import json
import uuid

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.mempalace.chroma_store import add

class ChromaInInput(BaseModel):
    text: str = Field(..., description="用户要求记住的信息")


def _configurable_from_run_manager(run_manager) -> dict:
    if run_manager is None:
        return {}
    cfg = getattr(run_manager, "config", None) or {}
    if not isinstance(cfg, dict):
        return {}
    configurable = cfg.get("configurable") or {}
    if not isinstance(configurable, dict):
        return {}
    return configurable


class ChromaInTool(BaseTool):
    name: str = "ChromaIn"
    description: str = "当用户提出需要记住的信息时，使用该工具"
    args_schema: type[BaseModel] = ChromaInInput

    def _run(self, text: str, *, run_manager=None, **_: object) -> str:
        configurable = _configurable_from_run_manager(run_manager)
        memory_id = uuid.uuid4().hex
        metadata = {
            "user_id": str(configurable.get("user_id") or "local"),
            "session_id": str(configurable.get("session_id") or "demo"),
        }
        try:
            add(memory_id, text, metadata)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
        return json.dumps(
            {"ok": True, "memory_id": memory_id, "metadata": metadata},
            ensure_ascii=False,
        )