from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.workspace.manager import WorkspaceManager


def test_delete_session_calls_checkpointer_and_removes_workspace(tmp_path, monkeypatch):
    ws_root = tmp_path / "workspace"
    test_mgr = WorkspaceManager(str(ws_root))
    monkeypatch.setattr("app.api.admin.manager", test_mgr)

    test_mgr.session_dir("alice", "chat-abc")
    assert (ws_root / "alice" / "chat-abc").is_dir()

    mock_cp = MagicMock()
    mock_cp.adelete_thread = AsyncMock()

    with TestClient(app) as client:
        client.app.state.checkpointer = mock_cp
        r = client.delete("/api/v2/sessions/chat-abc?user_id=alice")

    assert r.status_code == 200
    assert r.json()["ok"] is True
    mock_cp.adelete_thread.assert_awaited_once_with("chat-abc")
    assert not (ws_root / "alice" / "chat-abc").exists()


def test_delete_session_requires_checkpointer():
    with TestClient(app) as client:
        if hasattr(client.app.state, "checkpointer"):
            delattr(client.app.state, "checkpointer")
        r = client.delete("/api/v2/sessions/demo?user_id=local")
    assert r.status_code == 503


def test_delete_user_full(monkeypatch, tmp_path):
    deleted = {}

    def fake_delete(uid: str) -> None:
        deleted["user_id"] = uid

    monkeypatch.setattr("app.api.admin.chroma_store.delete_by_user", fake_delete)

    ws_root = tmp_path / "workspace"
    test_mgr = WorkspaceManager(str(ws_root))
    monkeypatch.setattr("app.api.admin.manager", test_mgr)
    test_mgr.session_dir("bob", "s1")

    from app.web_store.store import WebDataStore

    test_store = WebDataStore(tmp_path / "web")
    test_store.add_user("bob")
    test_store.create_session("bob", "chat-1")
    monkeypatch.setattr("app.api.admin.store", test_store)

    mock_cp = MagicMock()
    mock_cp.adelete_thread = AsyncMock()

    with TestClient(app) as client:
        client.app.state.checkpointer = mock_cp
        r = client.delete("/api/v2/users/bob")

    assert r.status_code == 200
    assert deleted["user_id"] == "bob"
    assert not (ws_root / "bob").exists()
    assert test_store.get_session("bob", "chat-1") is None
