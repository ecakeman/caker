"""MCP LangChain adapter must receive graph session_id via RunnableConfig."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.mcp.adapters.langchain import make_langchain_tool
from app.mcp.context import context_from_runnable_config
from app.mcp.registry import registry
from app.tools.base import build_default_tools


def test_context_from_runnable_config():
    cfg = {
        "configurable": {
            "user_id": "u1",
            "session_id": "s1",
            "thread_id": "s1",
        }
    }
    ctx = context_from_runnable_config(cfg)
    assert ctx.user_id == "u1"
    assert ctx.session_id == "s1"


def _patch_workspace_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.workspace.manager import WorkspaceManager

    mgr = WorkspaceManager(str(tmp_path))
    monkeypatch.setattr("app.workspace.manager.manager", mgr)
    monkeypatch.setattr("app.mcp.handlers._workspace.manager", mgr)
    return mgr


def test_read_tool_uses_invoke_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mgr = _patch_workspace_root(tmp_path, monkeypatch)
    session_id = "chat-test-session"
    mgr.session_dir("local", session_id)
    note = tmp_path / "local" / session_id / "data" / "uploads" / "note.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text("hello workspace", encoding="utf-8")

    defn = next(d for d in registry.list_definitions() if d.name == "read")
    tool = make_langchain_tool(registry, defn)
    config = {
        "configurable": {
            "user_id": "local",
            "session_id": session_id,
            "thread_id": session_id,
        }
    }
    out = tool.invoke(
        {"rel_path": "data/uploads/note.md", "offset": 0, "limit": 10},
        config=config,
    )
    assert "hello workspace" in out
    assert "<error>" not in out


def test_build_default_tools_respect_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mgr = _patch_workspace_root(tmp_path, monkeypatch)
    session_id = "chat-glob-session"
    mgr.session_dir("local", session_id)
    rag = tmp_path / "local" / session_id / "data" / "uploads" / "rag.md"
    rag.parent.mkdir(parents=True, exist_ok=True)
    rag.write_text("# RAG", encoding="utf-8")

    read_tool = next(t for t in build_default_tools() if t.name == "read")
    config = {
        "configurable": {
            "user_id": "local",
            "session_id": session_id,
            "thread_id": session_id,
        }
    }
    out = read_tool.invoke(
        {"rel_path": "data/uploads/rag.md", "offset": 0, "limit": 5},
        config=config,
    )
    assert "RAG" in out
