from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_mcp_list_tools():
    with TestClient(app) as client:
        r = client.get("/mcp/tools")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["tools"]}
    assert {"read", "write", "glob", "edit", "download"}.issubset(names)
    assert {"chroma_in", "chroma_out"}.issubset(names)


def test_mcp_call_write_and_read(tmp_path, monkeypatch):
    from app.workspace.manager import WorkspaceManager

    ws = tmp_path / "ws"
    monkeypatch.setattr("app.workspace.manager.manager", WorkspaceManager(str(ws)))
    monkeypatch.setattr("app.workspace.paths.manager", WorkspaceManager(str(ws)))

    with TestClient(app) as client:
        w = client.post(
            "/mcp/tools/call",
            json={
                "name": "write",
                "arguments": {"rel_path": "outputs/t.md", "content": "mcp"},
                "user_id": "u",
                "session_id": "s",
            },
        )
        assert w.status_code == 200
        assert w.json()["isError"] is False

        r = client.post(
            "/mcp/tools/call",
            json={
                "name": "read",
                "arguments": {"rel_path": "outputs/t.md"},
                "user_id": "u",
                "session_id": "s",
            },
        )
        assert r.status_code == 200
        assert "mcp" in r.json()["content"][0]["text"]
