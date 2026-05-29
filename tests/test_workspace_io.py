from __future__ import annotations

import pytest

from app.workspace.io import read_full_text, read_text_file, write_text_file
from app.workspace.manager import WorkspaceError, WorkspaceManager
from app.workspace.paths import MAX_TEXT_BYTES, assert_writable, normalize_rel_path


@pytest.fixture
def ws_mgr(tmp_path, monkeypatch):
    mgr = WorkspaceManager(str(tmp_path))
    monkeypatch.setattr("app.workspace.manager.manager", mgr)
    monkeypatch.setattr("app.workspace.paths.manager", mgr)
    mgr.session_dir("alice", "sess1")
    return mgr


def test_normalize_rel_path():
    assert normalize_rel_path("./data/x.txt") == "data/x.txt"
    assert normalize_rel_path("workspace/data/x.txt") == "data/x.txt"
    with pytest.raises(WorkspaceError):
        normalize_rel_path("../etc/passwd")


def test_assert_writable_compose():
    assert assert_writable("compose/docker-compose.yml") == "compose/docker-compose.yml"
    with pytest.raises(WorkspaceError):
        assert_writable("skills/foo.txt")


def test_write_and_read_roundtrip(ws_mgr):
    write_text_file("alice", "sess1", "data/note.txt", "hello\nworld")
    result = read_text_file("alice", "sess1", "data/note.txt", offset=0, limit=10)
    assert "hello" in result.text
    assert result.total_lines == 2


def test_read_normalizes_prefix(ws_mgr):
    write_text_file("alice", "sess1", "data/x.txt", "hi")
    result = read_text_file("alice", "sess1", "./workspace/data/x.txt")
    assert "hi" in result.text


def test_read_full_text(ws_mgr):
    write_text_file("alice", "sess1", "outputs/out.md", "# title")
    full = read_full_text("alice", "sess1", "outputs/out.md")
    assert full.content == "# title"
    assert full.rel_path == "outputs/out.md"


def test_write_compose(ws_mgr, tmp_path):
    result = write_text_file(
        "alice",
        "sess1",
        "compose/docker-compose.yml",
        "services: {}\n",
    )
    assert result.bytes_written > 0
    path = tmp_path / "alice" / "sess1" / "compose" / "docker-compose.yml"
    assert path.is_file()


def test_write_rejects_skills(ws_mgr):
    with pytest.raises(WorkspaceError):
        write_text_file("alice", "sess1", "skills/foo.txt", "x")


def test_write_size_limit(ws_mgr):
    big = "x" * (MAX_TEXT_BYTES + 1)
    with pytest.raises(WorkspaceError, match="too large"):
        write_text_file("alice", "sess1", "data/big.txt", big)


def test_read_pagination_hint(ws_mgr):
    content = "\n".join(f"line{i}" for i in range(250))
    write_text_file("alice", "sess1", "data/lines.txt", content)
    result = read_text_file("alice", "sess1", "data/lines.txt", offset=0, limit=200)
    assert "use offset=200" in result.text
