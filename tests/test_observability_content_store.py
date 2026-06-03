from __future__ import annotations

import pytest

from app.config import settings
from app.observability.content_store import spill_if_large
from app.observability.session_log import SessionLogContext


@pytest.fixture
def log_mgr(tmp_path, monkeypatch):
    from app.workspace.manager import WorkspaceManager

    mgr = WorkspaceManager(str(tmp_path))
    monkeypatch.setattr("app.workspace.manager.manager", mgr)
    monkeypatch.setattr("app.workspace.paths.manager", mgr)
    monkeypatch.setattr("app.observability.session_log.manager", mgr)
    monkeypatch.setattr("app.observability.content_store.manager", mgr)
    mgr.session_dir("u1", "s1")
    return mgr


def test_spill_small_inline(log_mgr, monkeypatch):
    monkeypatch.setattr(settings, "session_log_blob_threshold", 2048)
    ctx = SessionLogContext.from_ids("u1", "s1")
    assert spill_if_large(ctx, "hello", label="t") == "hello"


def test_spill_medium_preview_only(log_mgr, monkeypatch):
    monkeypatch.setattr(settings, "session_log_blob_threshold", 2048)
    ctx = SessionLogContext.from_ids("u1", "s1")
    text = "x" * 600
    out = spill_if_large(ctx, text, label="t")
    assert isinstance(out, dict)
    assert out["len"] == 600
    assert "ref" not in out


def test_spill_large_writes_blob(log_mgr, monkeypatch):
    monkeypatch.setattr(settings, "session_log_blob_threshold", 512)
    ctx = SessionLogContext.from_ids("u1", "s1")
    text = "y" * 3000
    out = spill_if_large(ctx, text, label="t")
    assert isinstance(out, dict)
    assert out.get("ref", "").startswith("logs/blobs/")
    blob = log_mgr.session_dir("u1", "s1") / out["ref"]
    assert blob.is_file()
    assert blob.read_text(encoding="utf-8") == text


def test_spill_deduplicates_same_content(log_mgr, monkeypatch):
    monkeypatch.setattr(settings, "session_log_blob_threshold", 512)
    ctx = SessionLogContext.from_ids("u1", "s1")
    text = "z" * 3000
    first = spill_if_large(ctx, text, label="a")
    second = spill_if_large(ctx, text, label="b")
    assert first["ref"] == second["ref"]
    blobs = list((log_mgr.session_dir("u1", "s1") / "logs" / "blobs").glob("*.txt"))
    assert len(blobs) == 1
