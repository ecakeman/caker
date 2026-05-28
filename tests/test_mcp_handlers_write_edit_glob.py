from __future__ import annotations

import json

import pytest

from app.mcp.registry import registry
from app.mcp.types import ToolContext
from app.workspace.manager import WorkspaceManager


@pytest.fixture
def ws_env(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    mgr = WorkspaceManager(str(root))
    monkeypatch.setattr("app.workspace.manager.manager", mgr)
    monkeypatch.setattr("app.mcp.handlers._workspace.manager", mgr)
    ctx = ToolContext(user_id="alice", session_id="sess1")
    mgr.session_dir("alice", "sess1")
    return ctx, root


def test_write_rejects_skills_path(ws_env):
    ctx, _ = ws_env
    res = registry.call_tool_sync(
        "write",
        {"rel_path": "skills/foo.txt", "content": "x"},
        ctx,
    )
    assert res.is_error
    assert "data/" in res.text or "outputs/" in res.text


def test_edit_unique_replace(ws_env):
    ctx, root = ws_env
    registry.call_tool_sync(
        "write",
        {"rel_path": "data/note.txt", "content": "alpha beta"},
        ctx,
    )
    res = registry.call_tool_sync(
        "edit",
        {"rel_path": "data/note.txt", "old_string": "beta", "new_string": "gamma"},
        ctx,
    )
    data = json.loads(res.text)
    assert data["ok"] is True
    text = (root / "alice" / "sess1" / "data" / "note.txt").read_text(encoding="utf-8")
    assert "gamma" in text


def test_glob_lists_files(ws_env):
    ctx, _ = ws_env
    registry.call_tool_sync("write", {"rel_path": "data/x.txt", "content": "1"}, ctx)
    res = registry.call_tool_sync("glob", {"pattern": "data/*.txt"}, ctx)
    assert "x.txt" in res.text
