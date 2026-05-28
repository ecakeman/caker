from __future__ import annotations

import pytest

from app.workspace.manager import WorkspaceError, WorkspaceManager


def test_session_dir_creates_user_session_layout(tmp_path):
    mgr = WorkspaceManager(str(tmp_path))
    ws = mgr.session_dir("local", "demo-s1")
    assert ws == tmp_path / "local" / "demo-s1"
    assert (ws / "data").is_dir()
    assert (ws / "outputs").is_dir()


def test_resolve_blocks_traversal(tmp_path):
    mgr = WorkspaceManager(str(tmp_path))
    with pytest.raises(WorkspaceError, match="path traversal"):
        mgr.resolve("u1", "s1", "../etc/passwd")


def test_remove_session_and_user_workspace(tmp_path):
    mgr = WorkspaceManager(str(tmp_path))
    mgr.session_dir("alice", "chat-1")
    mgr.session_dir("alice", "chat-2")
    mgr.session_dir("bob", "chat-3")

    mgr.remove_session_workspace("alice", "chat-1")
    assert not (tmp_path / "alice" / "chat-1").exists()
    assert (tmp_path / "alice" / "chat-2").exists()

    mgr.remove_user_workspace("alice")
    assert not (tmp_path / "alice").exists()
    assert (tmp_path / "bob" / "chat-3").exists()
