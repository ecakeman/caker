from __future__ import annotations

import json

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from app.mempalace.chroma_store import search


class ChromaOutInput(BaseModel):
    text: str = Field(..., description="用户要求搜索的信息")

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

class ChromaOutTool(BaseTool):
    name: str = "ChromaOut"
    description: str = "当用户提出需要回忆记住的信息时，使用该工具"
    args_schema: type[BaseModel] = ChromaOutInput

    def _run(self, text: str, *, run_manager=None, **_: object) -> str:
        configurable = _configurable_from_run_manager(run_manager)
        try:
            hits = search(text, k=3, where={"user_id": configurable.get("user_id") or "local"})
            items = [
                {"id": memory_id, "text": doc, "metadata": metadata}
                for memory_id, doc, metadata in hits
            ]
            return json.dumps({"ok": True, "count": len(items), "hits": items}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)