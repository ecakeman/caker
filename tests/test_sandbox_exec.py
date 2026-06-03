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
    monkeypatch.setattr("app.workspace.paths.manager", mgr)
    monkeypatch.setattr("app.execution.exec_runner.manager", mgr)
    monkeypatch.setattr("app.execution.sandbox_context.manager", mgr)
    monkeypatch.setattr("app.observability.session_log.manager", mgr)
    monkeypatch.setattr("app.observability.content_store.manager", mgr)
    ctx = ToolContext(user_id="alice", session_id="sess1")
    mgr.session_dir("alice", "sess1")
    return ctx, mgr


def test_sandbox_exec_propose(ws_env):
    ctx, _mgr = ws_env
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
    ctx, _mgr = ws_env
    res = registry.call_tool_sync("sandbox_exec", {"command": "vim foo"}, ctx)
    assert res.is_error


def test_approve_and_run_mock(ws_env):
    ctx, _mgr = ws_env
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


def test_propose_writes_sandbox_log(ws_env, monkeypatch):
    from app.config import settings

    ctx, mgr = ws_env
    monkeypatch.setattr(settings, "session_log_enabled", True)
    propose_exec(user_id=ctx.user_id, session_id=ctx.session_id, command="echo hi")
    log_path = mgr.session_dir(ctx.user_id, ctx.session_id) / "logs" / "sandbox.log"
    assert log_path.is_file()
    assert "[proposed]" in log_path.read_text(encoding="utf-8")


def test_run_one_shot_logs_engine_and_sandbox_log(ws_env, monkeypatch):
    from app.config import settings
    from app.execution.exec_runner import run_one_shot_command

    ctx, mgr = ws_env
    monkeypatch.setattr(settings, "session_log_enabled", True)

    class FakeProc:
        returncode = 0
        stdout = "hello-out\n"
        stderr = ""

    with patch("app.execution.exec_runner.subprocess.run", return_value=FakeProc()):
        with patch("app.execution.exec_runner.build_exec_argv", return_value=["echo"]):
            run_one_shot_command(
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                command="echo hello-out",
            )

    sandbox_log = mgr.session_dir(ctx.user_id, ctx.session_id) / "logs" / "sandbox.log"
    engine = mgr.session_dir(ctx.user_id, ctx.session_id) / "logs" / "engine.jsonl"
    assert "hello-out" in sandbox_log.read_text(encoding="utf-8")
    events = [json.loads(line)["event"] for line in engine.read_text(encoding="utf-8").strip().splitlines()]
    assert "sandbox_exec_done" in events


def test_write_large_args_spill(ws_env, monkeypatch):
    from app.config import settings

    ctx, mgr = ws_env
    monkeypatch.setattr(settings, "session_log_enabled", True)
    monkeypatch.setattr(settings, "session_log_blob_threshold", 512)
    big = "A" * 3000
    registry.call_tool_sync(
        "write",
        {"rel_path": "data/big.txt", "content": big},
        ctx,
    )
    engine = mgr.session_dir(ctx.user_id, ctx.session_id) / "logs" / "engine.jsonl"
    lines = engine.read_text(encoding="utf-8").strip().splitlines()
    rec = json.loads(lines[0])
    content_meta = rec["meta"]["args"]["content"]
    assert content_meta.get("ref", "").startswith("logs/blobs/")


def test_reject_pending(ws_env):
    ctx, _mgr = ws_env
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

    ctx, _mgr = ws_env
    block = build_sandbox_context(ctx.user_id, ctx.session_id)
    assert "[SANDBOX_CONTEXT]" in block
    assert "sandbox_mode: true" in block
