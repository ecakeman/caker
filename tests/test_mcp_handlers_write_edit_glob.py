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
    monkeypatch.setattr("app.workspace.paths.manager", mgr)
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
    assert "compose" in res.text or "data/" in res.text


def test_write_compose_path(ws_env):
    ctx, root = ws_env
    res = registry.call_tool_sync(
        "write",
        {"rel_path": "compose/docker-compose.yml", "content": "services: {}\n"},
        ctx,
    )
    data = json.loads(res.text)
    assert data["ok"] is True
    assert (root / "alice" / "sess1" / "compose" / "docker-compose.yml").is_file()


def test_read_normalizes_workspace_prefix(ws_env):
    ctx, _ = ws_env
    registry.call_tool_sync("write", {"rel_path": "data/x.txt", "content": "hi"}, ctx)
    res = registry.call_tool_sync("read", {"rel_path": "./workspace/data/x.txt"}, ctx)
    assert not res.is_error
    assert "hi" in res.text


def test_write_normalizes_dot_prefix(ws_env):
    ctx, root = ws_env
    res = registry.call_tool_sync(
        "write",
        {"rel_path": "./data/nested.txt", "content": "ok"},
        ctx,
    )
    assert json.loads(res.text)["ok"] is True
    assert (root / "alice" / "sess1" / "data" / "nested.txt").read_text() == "ok"


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
