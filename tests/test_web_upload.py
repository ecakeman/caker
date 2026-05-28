from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_upload_file_to_session_workspace(tmp_path, monkeypatch):
    from app.workspace.manager import WorkspaceManager

    monkeypatch.setattr("app.workspace.manager.manager", WorkspaceManager(str(tmp_path / "ws")))

    with TestClient(app) as client:
        r = client.post(
            "/api/v2/web/sessions/s1/upload",
            params={"user_id": "u1"},
            files=[("files", ("notes.txt", b"hello file", "text/plain"))],
        )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert len(data["files"]) == 1
    assert data["files"][0]["rel_path"] == "data/uploads/notes.txt"
    assert data["files"][0]["bytes"] == 10


def test_upload_rejects_oversize(tmp_path, monkeypatch):
    from app.config import settings
    from app.workspace.manager import WorkspaceManager

    monkeypatch.setattr(settings, "upload_max_bytes", 5)
    monkeypatch.setattr("app.workspace.manager.manager", WorkspaceManager(str(tmp_path / "ws")))

    with TestClient(app) as client:
        r = client.post(
            "/api/v2/web/sessions/s1/upload",
            params={"user_id": "u1"},
            files=[("files", ("big.bin", b"12345678", "application/octet-stream"))],
        )
    assert r.status_code == 400
