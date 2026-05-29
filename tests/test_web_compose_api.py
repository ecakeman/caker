from fastapi.testclient import TestClient

from app.main import app
from app.workspace.manager import manager


def test_compose_status_api(tmp_path, monkeypatch):
    monkeypatch.setattr(manager, "root", tmp_path)
    uid, sid = "u1", "s1"
    ws = manager.session_dir(uid, sid)
    compose = ws / "compose" / "docker-compose.yml"
    compose.parent.mkdir(parents=True, exist_ok=True)
    compose.write_text("services:\n  dev:\n    image: python:3.12-slim\n", encoding="utf-8")

    monkeypatch.setattr(
        "app.execution.compose_control.docker_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.execution.compose_control.compose_ps_has_running",
        lambda *_: False,
    )

    client = TestClient(app)
    res = client.get(
        f"/api/v2/web/sessions/{sid}/compose/status",
        params={"user_id": uid},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["running"] is False


def test_compose_up_api(tmp_path, monkeypatch):
    monkeypatch.setattr(manager, "root", tmp_path)
    uid, sid = "u1", "s1"
    ws = manager.session_dir(uid, sid)
    compose = ws / "compose" / "docker-compose.yml"
    compose.parent.mkdir(parents=True, exist_ok=True)
    compose.write_text("services:\n  dev:\n    image: python:3.12-slim\n", encoding="utf-8")

    monkeypatch.setattr(
        "app.execution.compose_control.compose_up",
        lambda u, s: {
            "ok": True,
            "running": True,
            "compose_file": "compose/docker-compose.yml",
            "project": "caker-u1-s1",
            "stdout": "ok",
            "stderr": "",
        },
    )

    client = TestClient(app)
    res = client.post(
        f"/api/v2/web/sessions/{sid}/compose/up",
        params={"user_id": uid},
    )
    assert res.status_code == 200
    assert res.json()["running"] is True
