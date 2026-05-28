from __future__ import annotations

import pytest

from app.mcp.registry import registry
from app.mcp.types import ToolContext


def test_all_registered_tools_have_object_schema():
    for tool in registry.list_tools_public(include_result_set=True):
        schema = tool["inputSchema"]
        assert schema.get("type") == "object", tool["name"]
        assert isinstance(tool["name"], str) and tool["name"]


def test_default_tools_include_chroma_exclude_result_set():
    names = [t.name for t in registry.to_langchain_tools(include_result_set=False)]
    assert "read" in names
    assert "write" in names
    assert "chroma_in" in names
    assert "chroma_out" in names
    assert "ChromaIn" not in names
    assert "result_set" not in names


def test_call_read_write_glob_smoke(tmp_path, monkeypatch):
    from app.workspace.manager import WorkspaceManager

    ws = tmp_path / "ws"
    monkeypatch.setattr("app.workspace.manager.manager", WorkspaceManager(str(ws)))
    monkeypatch.setattr("app.mcp.handlers._workspace.manager", WorkspaceManager(str(ws)))

    ctx = ToolContext(user_id="u1", session_id="s1")
    ws_mgr = WorkspaceManager(str(ws))
    ws_mgr.session_dir("u1", "s1")
    (ws / "u1" / "s1" / "data" / "a.txt").write_text("hello\nworld", encoding="utf-8")

    read_res = registry.call_tool_sync("read", {"rel_path": "data/a.txt", "offset": 0, "limit": 10}, ctx)
    assert "hello" in read_res.text

    write_res = registry.call_tool_sync(
        "write",
        {"rel_path": "outputs/out.md", "content": "# hi"},
        ctx,
    )
    assert '"ok": true' in write_res.text

    glob_res = registry.call_tool_sync("glob", {"pattern": "data/*.txt"}, ctx)
    assert "a.txt" in glob_res.text


def test_call_skill_demo_hello():
    skills_manager_reindex()
    ctx = ToolContext()
    res = registry.call_tool_sync("call_skill", {"skill_name": "demo-hello"}, ctx)
    assert "demo-hello" in res.text
    assert "instructions" in res.text


def skills_manager_reindex():
    from app.skills.manager import skills_manager

    skills_manager.reindex()
