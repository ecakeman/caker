from fastapi.testclient import TestClient

from app.main import app
from app.workspace.manager import manager


def test_put_workspace_file(tmp_path, monkeypatch):
    monkeypatch.setattr(manager, "root", tmp_path)
    client = TestClient(app)
    uid, sid = "u1", "s1"
    ws = manager.session_dir(uid, sid)
    target = ws / "data" / "hello.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("old", encoding="utf-8")

    res = client.put(
        f"/api/v2/web/sessions/{sid}/workspace/file",
        params={"user_id": uid, "path": "data/hello.txt"},
        json={"content": "new content\nline2"},
    )
    assert res.status_code == 200
    assert target.read_text(encoding="utf-8") == "new content\nline2"


def test_put_compose_file(tmp_path, monkeypatch):
    monkeypatch.setattr(manager, "root", tmp_path)
    client = TestClient(app)
    uid, sid = "u1", "s1"
    manager.session_dir(uid, sid)

    res = client.put(
        f"/api/v2/web/sessions/{sid}/workspace/file",
        params={"user_id": uid, "path": "compose/docker-compose.yml"},
        json={"content": "services:\n  dev:\n    image: python:3.12-slim\n"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["path"] == "compose/docker-compose.yml"


def test_put_normalizes_path(tmp_path, monkeypatch):
    monkeypatch.setattr(manager, "root", tmp_path)
    client = TestClient(app)
    uid, sid = "u1", "s1"
    ws = manager.session_dir(uid, sid)

    res = client.put(
        f"/api/v2/web/sessions/{sid}/workspace/file",
        params={"user_id": uid, "path": "./data/nested.txt"},
        json={"content": "normalized"},
    )
    assert res.status_code == 200
    assert (ws / "data" / "nested.txt").read_text(encoding="utf-8") == "normalized"


def test_get_matches_agent_write(tmp_path, monkeypatch):
    monkeypatch.setattr(manager, "root", tmp_path)
    from app.mcp.registry import registry
    from app.mcp.types import ToolContext

    uid, sid = "u1", "s1"
    manager.session_dir(uid, sid)
    registry.call_tool_sync(
        "write",
        {"rel_path": "data/agent.txt", "content": "from agent"},
        ToolContext(user_id=uid, session_id=sid),
    )

    client = TestClient(app)
    res = client.get(
        f"/api/v2/web/sessions/{sid}/workspace/file",
        params={"user_id": uid, "path": "data/agent.txt"},
    )
    assert res.status_code == 200
    assert res.json()["content"] == "from agent"
