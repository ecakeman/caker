from __future__ import annotations

from pathlib import Path

import pytest

from app.workspace.fs_ops import FsOpsError, copy_entry, delete_entry, mkdir, move_entry
from app.workspace.manager import WorkspaceManager


@pytest.fixture
def ws_mgr(tmp_path, monkeypatch):
    mgr = WorkspaceManager(str(tmp_path))
    monkeypatch.setattr("app.workspace.manager.manager", mgr)
    monkeypatch.setattr("app.workspace.paths.manager", mgr)
    monkeypatch.setattr("app.workspace.fs_ops.manager", mgr)
    mgr.session_dir("alice", "sess1")
    return mgr, tmp_path


def test_mkdir_under_data(ws_mgr):
    result = mkdir("alice", "sess1", "data/sub/nested")
    assert result["ok"] is True
    assert result["path"] == "data/sub/nested"


def test_mkdir_rejects_skills(ws_mgr):
    from app.workspace.manager import WorkspaceError

    with pytest.raises(WorkspaceError):
        mkdir("alice", "sess1", "skills/foo")


def test_copy_file(ws_mgr, tmp_path):
    ws = tmp_path / "alice" / "sess1"
    src = ws / "data" / "a.txt"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("hi", encoding="utf-8")

    result = copy_entry("alice", "sess1", "data/a.txt", "outputs")
    assert result["ok"] is True
    assert (ws / "outputs" / "a.txt").read_text(encoding="utf-8") == "hi"


def test_move_rename(ws_mgr, tmp_path):
    ws = tmp_path / "alice" / "sess1"
    src = ws / "data" / "old.txt"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("x", encoding="utf-8")

    result = move_entry("alice", "sess1", "data/old.txt", "data/new.txt")
    assert result["dest"] == "data/new.txt"
    assert not src.exists()
    assert (ws / "data" / "new.txt").is_file()


def test_delete_empty_dir(ws_mgr, tmp_path):
    ws = tmp_path / "alice" / "sess1"
    d = ws / "data" / "empty"
    d.mkdir(parents=True)
    delete_entry("alice", "sess1", "data/empty")
    assert not d.exists()


def test_delete_nonempty_dir_fails(ws_mgr, tmp_path):
    ws = tmp_path / "alice" / "sess1"
    d = ws / "data" / "full"
    d.mkdir(parents=True)
    (d / "x.txt").write_text("1", encoding="utf-8")
    with pytest.raises(FsOpsError, match="not empty"):
        delete_entry("alice", "sess1", "data/full")
