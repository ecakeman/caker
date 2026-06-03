from __future__ import annotations

import json

import pytest

from app.config import settings
from app.mcp.registry import registry
from app.mcp.types import ToolContext
from app.workspace.manager import WorkspaceManager


@pytest.fixture
def log_env(tmp_path, monkeypatch):
    mgr = WorkspaceManager(str(tmp_path / "ws"))
    monkeypatch.setattr("app.workspace.manager.manager", mgr)
    monkeypatch.setattr("app.workspace.paths.manager", mgr)
    monkeypatch.setattr("app.observability.session_log.manager", mgr)
    monkeypatch.setattr("app.observability.content_store.manager", mgr)
    monkeypatch.setattr(settings, "session_log_enabled", True)
    monkeypatch.setattr(settings, "session_log_blob_threshold", 1024)
    ctx = ToolContext(user_id="u1", session_id="s1")
    mgr.session_dir("u1", "s1")
    return ctx, mgr


def test_tool_start_end_share_run_id(log_env):
    ctx, mgr = log_env
    registry.call_tool_sync("get_current_time", {}, ctx)
    engine = mgr.session_dir("u1", "s1") / "logs" / "engine.jsonl"
    lines = [json.loads(l) for l in engine.read_text(encoding="utf-8").strip().splitlines()]
    start = next(r for r in lines if r["event"] == "tool_start")
    end = next(r for r in lines if r["event"] == "tool_end")
    assert start["meta"]["run_id"] == end["meta"]["run_id"]
    assert start["msg"] == end["msg"] == "get_current_time"


def test_tool_end_preview_max_200(log_env):
    from app.observability.content_store import encode_tool_result
    from app.observability.session_log import SessionLogContext

    ctx_obj = SessionLogContext.from_ids("u1", "s1")
    meta = encode_tool_result(ctx_obj, "a" * 500)
    assert len(meta["preview"]) <= 201


def test_tool_end_error_uses_preview(log_env):
    ctx, mgr = log_env
    registry.call_tool_sync("read", {"rel_path": "data/missing.txt"}, ctx)
    engine = mgr.session_dir("u1", "s1") / "logs" / "engine.jsonl"
    end = json.loads(engine.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert end["meta"]["is_error"] is True
    assert "preview" in end["meta"]
    assert "error" not in end["meta"]
    assert "ok" in end["meta"]["preview"] or "false" in end["meta"]["preview"].lower()
