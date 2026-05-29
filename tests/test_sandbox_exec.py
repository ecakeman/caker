from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.execution.exec_pending import approve_and_run, propose_exec, reject_pending
from app.mcp.registry import registry
from app.mcp.types import ToolContext
from app.workspace.manager import WorkspaceManager


@pytest.fixture
def ws_env(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    mgr = WorkspaceManager(str(root))
    monkeypatch.setattr("app.workspace.manager.manager", mgr)
    monkeypatch.setattr("app.workspace.manager.manager", mgr)
    monkeypatch.setattr("app.workspace.paths.manager", mgr)
    monkeypatch.setattr("app.execution.exec_runner.manager", mgr)
    monkeypatch.setattr("app.execution.sandbox_context.manager", mgr)
    ctx = ToolContext(user_id="alice", session_id="sess1")
    mgr.session_dir("alice", "sess1")
    return ctx, root


def test_sandbox_exec_propose(ws_env):
    ctx, _ = ws_env
    res = registry.call_tool_sync(
        "sandbox_exec",
        {"command": "echo hello", "timeout_sec": 30},
        ctx,
    )
    assert not res.is_error
    data = json.loads(res.text)
    assert data["ok"] is True
    assert data["status"] == "awaiting_user_confirmation"
    assert data["pending_id"]


def test_sandbox_exec_rejects_interactive(ws_env):
    ctx, _ = ws_env
    res = registry.call_tool_sync("sandbox_exec", {"command": "vim foo"}, ctx)
    assert res.is_error


def test_approve_and_run_mock(ws_env):
    ctx, _ = ws_env
    pending = propose_exec(
        user_id=ctx.user_id,
        session_id=ctx.session_id,
        command="echo ok",
    )
    with patch(
        "app.execution.exec_pending.run_one_shot_command",
        return_value={"ok": True, "exit_code": 0, "stdout": "ok\n", "stderr": "", "command": "echo ok"},
    ):
        result = approve_and_run(
            pending.pending_id,
            user_id=ctx.user_id,
            session_id=ctx.session_id,
        )
    assert result["exit_code"] == 0
    assert "ok" in result["stdout"]


def test_reject_pending(ws_env):
    ctx, _ = ws_env
    pending = propose_exec(
        user_id=ctx.user_id,
        session_id=ctx.session_id,
        command="echo x",
    )
    reject_pending(
        pending.pending_id,
        user_id=ctx.user_id,
        session_id=ctx.session_id,
    )
    res = registry.call_tool_sync("sandbox_exec", {"command": "echo y"}, ctx)
    data = json.loads(res.text)
    assert data["pending_id"] != pending.pending_id


def test_build_sandbox_context(ws_env):
    from app.execution.sandbox_context import build_sandbox_context

    ctx, _ = ws_env
    block = build_sandbox_context(ctx.user_id, ctx.session_id)
    assert "[SANDBOX_CONTEXT]" in block
    assert "sandbox_mode: true" in block
