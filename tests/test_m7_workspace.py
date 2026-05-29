from __future__ import annotations

import shutil

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


def test_force_rmtree_chmod_readonly_files(tmp_path):
    mgr = WorkspaceManager(str(tmp_path))
    ws = mgr.session_dir("alice", "chat-ro")
    target = ws / "data" / "pkg"
    target.mkdir(parents=True)
    pyc = target / "__init__.cpython-312.pyc"
    pyc.write_bytes(b"\x00")
    pyc.chmod(0o444)

    mgr.remove_session_workspace("alice", "chat-ro")
    assert not (tmp_path / "alice" / "chat-ro").exists()


def test_force_rmtree_falls_back_to_docker(tmp_path, monkeypatch):
    mgr = WorkspaceManager(str(tmp_path))
    ws = mgr.session_dir("alice", "chat-docker")
    called: list[Path] = []
    real_rmtree = shutil.rmtree

    def fake_docker_rmtree(path: Path) -> None:
        called.append(path)
        real_rmtree(path)

    monkeypatch.setattr("app.workspace.manager._docker_rmtree", fake_docker_rmtree)

    def fail_rmtree(_path, onexc=None):
        raise PermissionError("simulated root-owned file")

    monkeypatch.setattr("app.workspace.manager.shutil.rmtree", fail_rmtree)

    mgr.remove_session_workspace("alice", "chat-docker")
    assert called == [ws]
    assert not ws.exists()
