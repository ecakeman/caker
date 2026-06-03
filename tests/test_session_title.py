from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.web_store.store import WebDataStore
from app.web.session_title import (
    DEFAULT_SESSION_TITLE,
    format_dialog_for_title,
    generate_session_title,
    normalize_title,
    should_generate_title,
    title_needs_generation,
)


def test_normalize_title_strips_quotes_and_punctuation():
    assert normalize_title('"Servlet 入门"') == "Servlet 入门"
    assert normalize_title("标题：文档解读。") == "文档解读"


def test_format_dialog_skips_attachment_lines():
    dialog = format_dialog_for_title(
        [
            {"role": "user", "content": "你好\n[文件] data/a.pdf"},
            {"role": "assistant", "content": "这是 servlet 说明"},
        ]
    )
    assert "data/a.pdf" not in dialog
    assert "servlet" in dialog


def test_format_dialog_uses_first_exchange_only():
    dialog = format_dialog_for_title(
        [
            {"role": "user", "content": "第一句"},
            {"role": "assistant", "content": "第一次回复"},
            {"role": "user", "content": "第二句"},
            {"role": "assistant", "content": "不应出现"},
        ]
    )
    assert "第一句" in dialog
    assert "第一次回复" in dialog
    assert "第二句" not in dialog
    assert "不应出现" not in dialog


def test_title_needs_generation_only_once():
    session = {
        "title": "已有标题",
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ],
    }
    assert title_needs_generation(session) is False

    session2 = {
        "title": DEFAULT_SESSION_TITLE,
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ],
    }
    assert title_needs_generation(session2) is True


def test_should_generate_title_requires_both_roles():
    assert should_generate_title([{"role": "user", "content": "hi"}]) is False
    assert should_generate_title(
        [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
    )


def test_generate_session_title_calls_llm():
    messages = [
        {"role": "user", "content": "servlet是什么"},
        {"role": "assistant", "content": "Servlet 是 Java Web 组件…"},
    ]
    with patch("app.web.session_title.get_llm") as mock_llm:
        mock_llm.return_value.invoke.return_value.content = "Java Servlet 简介"
        title = generate_session_title(messages, user_id="alice")
    assert title == "Java Servlet 简介"


def test_generate_title_endpoint(tmp_path, monkeypatch):
    test_store = WebDataStore(tmp_path / "web")
    monkeypatch.setattr("app.api.web_data.store", test_store)

    test_store.ensure_dirs()
    test_store.add_user("alice")
    session = test_store.create_session("alice", "chat-title-1")
    session["messages"] = [
        {"role": "user", "content": "带我解读一下这份文档", "ts": 1},
        {"role": "assistant", "content": "文档讲的是执行环境架构…", "ts": 2},
    ]
    test_store.save_session(session)

    with patch(
        "app.api.web_data.generate_session_title",
        return_value="执行环境文档解读",
    ):
        with TestClient(app) as client:
            r = client.post(
                "/api/v2/web/sessions/chat-title-1/generate-title?user_id=alice",
            )
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "执行环境文档解读"
    assert body["session"]["title"] == "执行环境文档解读"
