from __future__ import annotations

import json

import pytest

from app.config import settings
from app.observability.session_log import (
    SessionLogContext,
    _sanitize_meta,
    append_engine,
    append_sandbox_log,
    append_terminal_bytes,
    log_for_ids,
)
from app.workspace.io import read_text_file
from app.workspace.manager import WorkspaceManager
from app.workspace.paths import assert_readable, assert_writable


@pytest.fixture
def log_mgr(tmp_path, monkeypatch):
    mgr = WorkspaceManager(str(tmp_path))
    monkeypatch.setattr("app.workspace.manager.manager", mgr)
    monkeypatch.setattr("app.workspace.paths.manager", mgr)
    monkeypatch.setattr("app.observability.session_log.manager", mgr)
    mgr.session_dir("u1", "s1")
    return mgr


def test_logs_readable_not_writable(log_mgr):
    assert assert_readable("logs/engine.jsonl") == "logs/engine.jsonl"
    with pytest.raises(Exception):
        assert_writable("logs/x.txt")


def test_append_engine_jsonl(log_mgr, monkeypatch):
    monkeypatch.setattr(settings, "session_log_enabled", True)
    ctx = log_for_ids("u1", "s1")
    append_engine(ctx, "tool_start", "read", meta={"path": "data/x.txt"})
    path = log_mgr.session_dir("u1", "s1") / "logs" / "engine.jsonl"
    assert path.is_file()
    line = path.read_text(encoding="utf-8").strip().splitlines()[-1]
    rec = json.loads(line)
    assert rec["event"] == "tool_start"
    assert rec["source"] == "engine"
    assert rec["meta"]["path"] == "data/x.txt"


def test_agent_log_disabled_by_default(log_mgr, monkeypatch):
    from app.observability.session_log import append_agent

    monkeypatch.setattr(settings, "session_log_enabled", True)
    monkeypatch.setattr(settings, "session_agent_log_enabled", False)
    ctx = SessionLogContext.from_ids("u1", "s1")
    append_agent(ctx, "stream_delta", "batch")
    path = log_mgr.session_dir("u1", "s1") / "logs" / "agent.jsonl"
    assert not path.exists()


def test_rotate(log_mgr, monkeypatch):
    monkeypatch.setattr(settings, "session_log_enabled", True)
    monkeypatch.setattr(settings, "session_log_max_bytes", 80)
    ctx = log_for_ids("u1", "s1")
    for i in range(5):
        append_engine(ctx, "ping", f"msg-{i}", meta={"i": i})
    log_dir = log_mgr.session_dir("u1", "s1") / "logs"
    assert (log_dir / "engine.jsonl").exists() or (log_dir / "engine.jsonl.1").exists()


def test_terminal_append(log_mgr, monkeypatch):
    monkeypatch.setattr(settings, "session_log_enabled", True)
    ctx = log_for_ids("u1", "s1")
    append_terminal_bytes(ctx, b"hello\n")
    path = log_mgr.session_dir("u1", "s1") / "logs" / "sandbox.terminal.log"
    assert path.read_bytes() == b"hello\n"


def test_read_logs_via_io(log_mgr, monkeypatch):
    monkeypatch.setattr(settings, "session_log_enabled", True)
    append_engine(log_for_ids("u1", "s1"), "test", "ok")
    result = read_text_file("u1", "s1", "logs/engine.jsonl")
    assert "test" in result.text


def test_token_meta_not_redacted():
    meta = _sanitize_meta({"prompt_tokens": 42, "completion_tokens": 7, "password": "x"})
    assert meta["prompt_tokens"] == 42
    assert meta["completion_tokens"] == 7
    assert meta["password"] == "***"


def test_append_sandbox_log(log_mgr, monkeypatch):
    monkeypatch.setattr(settings, "session_log_enabled", True)
    ctx = log_for_ids("u1", "s1")
    append_sandbox_log(ctx, "2026-01-01T00:00:00Z [proposed] echo hi")
    path = log_mgr.session_dir("u1", "s1") / "logs" / "sandbox.log"
    assert path.is_file()
    assert "echo hi" in path.read_text(encoding="utf-8")


def test_blobs_readable(log_mgr, monkeypatch):
    from app.observability.content_store import spill_if_large

    monkeypatch.setattr(settings, "session_log_enabled", True)
    monkeypatch.setattr(settings, "session_log_blob_threshold", 256)
    ctx = log_for_ids("u1", "s1")
    out = spill_if_large(ctx, "b" * 1000, label="t")
    assert assert_readable(out["ref"]) == out["ref"]
