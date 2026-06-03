"""Tests for daemon, file watch, and user profile features."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.execution.daemon import start_daemon
from app.execution.file_watch import start_watch, stop_watch
from app.mcp.registry import registry
from app.mcp.types import ToolContext
from app.user_profile.store import (
    append_preference,
    build_user_profile_context,
    ensure_profile_link,
    load_profile_for_prompt,
    reflect_from_messages,
    user_profile_path,
)
from app.workspace.manager import WorkspaceManager


@pytest.fixture
def ws_env(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    mgr = WorkspaceManager(str(root))
    monkeypatch.setattr("app.workspace.manager.manager", mgr)
    monkeypatch.setattr("app.workspace.paths.manager", mgr)
    monkeypatch.setattr("app.execution.exec_runner.manager", mgr)
    monkeypatch.setattr("app.execution.daemon.manager", mgr)
    monkeypatch.setattr("app.execution.file_watch.manager", mgr)
    monkeypatch.setattr("app.execution.sandbox_context.manager", mgr)
    monkeypatch.setattr("app.user_profile.store.manager", mgr)
    monkeypatch.setattr("app.observability.session_log.manager", mgr)
    ctx = ToolContext(user_id="alice", session_id="sess1")
    mgr.session_dir("alice", "sess1")
    return ctx, mgr


def test_user_profile_append_and_prompt(ws_env):
    ctx, mgr = ws_env
    append_preference(ctx.user_id, "用户偏好：日志分析优先 tail", source_session=ctx.session_id)
    text = load_profile_for_prompt(ctx.user_id)
    assert "tail" in text
    block = build_user_profile_context(ctx.user_id)
    assert "[USER_PROFILE]" in block

    link = mgr.session_dir(ctx.user_id, ctx.session_id) / "logs" / "user_profile.jsonl"
    ensure_profile_link(ctx.user_id, ctx.session_id)
    assert link.is_symlink()
    assert user_profile_path(ctx.user_id).is_file()


def test_user_profile_reflect_dedupes(ws_env, monkeypatch):
    ctx, _mgr = ws_env
    append_preference(ctx.user_id, "用户偏好：别用表格")
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(
        content='{"preferences": ["用户偏好：别用表格", "用户偏好：简短回答"]}'
    )
    monkeypatch.setattr("app.runtime.llm.get_llm", lambda _uid: mock_llm)
    reflect_from_messages(
        ctx.user_id,
        ctx.session_id,
        [HumanMessage(content="别用表格"), AIMessage(content="好的")],
    )
    entries = user_profile_path(ctx.user_id).read_text(encoding="utf-8").strip().splitlines()
    prefs = [json.loads(line)["preference"] for line in entries]
    assert prefs.count("用户偏好：别用表格") == 1
    assert "用户偏好：简短回答" in prefs


def test_daemon_start_mock(ws_env):
    ctx, mgr = ws_env

    class FakeProc:
        returncode = 0
        stdout = "nohup\n"
        stderr = ""

    with patch("app.execution.daemon._run_in_container", return_value=FakeProc()):
        out = start_daemon(
            user_id=ctx.user_id,
            session_id=ctx.session_id,
            name="train",
            command="python train.py",
        )
    assert out["ok"] is True
    assert out["name"] == "train"
    reg = mgr.session_dir(ctx.user_id, ctx.session_id) / "logs" / "daemons" / "registry.json"
    assert reg.is_file()
    data = json.loads(reg.read_text(encoding="utf-8"))
    assert data["daemons"][0]["name"] == "train"


def test_daemon_mcp_tools_registered(ws_env):
    ctx, _mgr = ws_env
    names = {d.name for d in registry.list_definitions()}
    for n in ("daemon_start", "daemon_list", "daemon_attach", "daemon_stop"):
        assert n in names

    with patch(
        "app.mcp.handlers.daemon_tools.start_daemon",
        return_value={"ok": True, "name": "job", "mode": "nohup", "log_path": "logs/daemons/job.log"},
    ):
        res = registry.call_tool_sync(
            "daemon_start",
            {"name": "job", "command": "sleep 999"},
            ctx,
        )
    assert not res.is_error
    assert json.loads(res.text)["name"] == "job"


def test_file_watch_events(ws_env):
    ctx, mgr = ws_env
    target = mgr.session_dir(ctx.user_id, ctx.session_id) / "logs" / "engine.jsonl"
    target.write_text('{"event":"boot"}\n', encoding="utf-8")

    out = start_watch(
        user_id=ctx.user_id,
        session_id=ctx.session_id,
        paths=["logs/engine.jsonl"],
        poll_interval_sec=0.5,
    )
    watch_id = out["watch_id"]
    time.sleep(1.2)
    target.write_text('{"event":"boot"}\n{"event":"tool_start"}\n', encoding="utf-8")
    time.sleep(1.2)
    stop_watch(user_id=ctx.user_id, session_id=ctx.session_id, watch_id=watch_id)

    events_path = mgr.session_dir(ctx.user_id, ctx.session_id) / "logs" / "watch_events.jsonl"
    lines = events_path.read_text(encoding="utf-8").strip().splitlines()
    events = [json.loads(line)["event"] for line in lines]
    assert "watch_start" in events
    assert "modify" in events
    assert "watch_stop" in events


def test_watch_mcp_start_stop(ws_env):
    ctx, _mgr = ws_env
    res = registry.call_tool_sync(
        "watch_start",
        {"paths": ["logs/sandbox.log"], "poll_interval_sec": 1},
        ctx,
    )
    data = json.loads(res.text)
    assert data["ok"] is True
    watch_id = data["watch_id"]

    listed = json.loads(registry.call_tool_sync("watch_list", {}, ctx).text)
    assert any(w["watch_id"] == watch_id for w in listed["watches"])

    stopped = json.loads(
        registry.call_tool_sync("watch_stop", {"watch_id": watch_id}, ctx).text
    )
    assert stopped["stopped"] is True


def test_build_prompt_context_includes_profile(ws_env):
    from app.execution.sandbox_context import build_prompt_context

    ctx, _mgr = ws_env
    append_preference(ctx.user_id, "用户偏好：用 jq 解析 JSON")
    block = build_prompt_context(ctx.user_id, ctx.session_id, include_sandbox=False)
    assert "jq" in block
    assert "[USER_PROFILE]" in block
