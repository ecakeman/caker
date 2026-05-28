from __future__ import annotations

from app.web_store.store import WebDataStore, WebStoreError


def test_users_and_sessions_roundtrip(tmp_path):
    s = WebDataStore(tmp_path / "web")
    s.ensure_dirs()
    s.add_user("alice")
    session = s.create_session("alice")
    session["messages"] = [{"role": "user", "content": "hi", "ts": 1}]
    s.save_session(session)

    listed = s.list_sessions("alice")
    assert len(listed) == 1
    assert listed[0]["id"] == session["id"]

    loaded = s.get_session("alice", session["id"])
    assert loaded is not None
    assert loaded["messages"][0]["content"] == "hi"

    s.delete_session("alice", session["id"])
    assert s.get_session("alice", session["id"]) is None


def test_delete_user_removes_sessions(tmp_path):
    s = WebDataStore(tmp_path / "web")
    s.add_user("bob")
    s.create_session("bob", "chat-1")
    s.delete_all_sessions_for_user("bob")
    s.remove_user("bob")
    assert s.list_users() == []
    assert not (s.sessions_root / "bob").exists()


def test_invalid_user_id(tmp_path):
    s = WebDataStore(tmp_path / "web")
    try:
        s.add_user("bad id")
    except WebStoreError:
        pass
    else:
        raise AssertionError("expected WebStoreError")
