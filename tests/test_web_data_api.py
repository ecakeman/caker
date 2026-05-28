from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.web_store.store import WebDataStore


def test_web_users_and_sessions_api(tmp_path, monkeypatch):
    test_store = WebDataStore(tmp_path / "web")
    monkeypatch.setattr("app.api.web_data.store", test_store)
    monkeypatch.setattr("app.api.admin.store", test_store)

    with TestClient(app) as client:
        r = client.get("/api/v2/web/users")
        assert r.status_code == 200
        assert any(u["id"] == "local" for u in r.json()["users"])

        r = client.post("/api/v2/web/users", json={"id": "Sancho"})
        assert r.status_code == 200

        r = client.post("/api/v2/web/sessions", json={"user_id": "Sancho"})
        assert r.status_code == 200
        sid = r.json()["session"]["id"]

        r = client.put(
            f"/api/v2/web/sessions/{sid}",
            json={
                "id": sid,
                "title": "测试",
                "userId": "Sancho",
                "messages": [{"role": "user", "content": "hello", "ts": 1}],
            },
        )
        assert r.status_code == 200

        r = client.get(f"/api/v2/web/sessions/{sid}?user_id=Sancho")
        assert r.json()["session"]["title"] == "测试"
