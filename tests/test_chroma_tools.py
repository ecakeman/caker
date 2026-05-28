from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from app.tools.chroma_in_tool import ChromaInTool
from app.tools.chroma_out_tool import ChromaOutTool


def test_chroma_in_tool_writes_with_config_metadata():
    tool = ChromaInTool()
    run_manager = SimpleNamespace(
        config={"configurable": {"user_id": "u1", "session_id": "s1"}}
    )
    fake_uuid = SimpleNamespace(hex="mid123")

    with patch("app.tools.chroma_in_tool.uuid.uuid4", return_value=fake_uuid), patch(
        "app.tools.chroma_in_tool.add"
    ) as mock_add:
        out = tool._run("remember this", run_manager=run_manager)

    data = json.loads(out)
    assert data == {
        "ok": True,
        "memory_id": "mid123",
        "metadata": {"user_id": "u1", "session_id": "s1"},
    }
    mock_add.assert_called_once_with(
        "mid123",
        "remember this",
        {"user_id": "u1", "session_id": "s1"},
    )


def test_chroma_in_tool_returns_error_payload_on_failure():
    tool = ChromaInTool()
    with patch("app.tools.chroma_in_tool.add", side_effect=RuntimeError("boom")):
        out = tool._run("remember this", run_manager=None)
    data = json.loads(out)
    assert data["ok"] is False
    assert "boom" in data["error"]


def test_chroma_out_tool_returns_structured_hits():
    tool = ChromaOutTool()
    run_manager = SimpleNamespace(config={"configurable": {"user_id": "u1"}})
    hits = [("id1", "doc1", {"user_id": "u1"})]

    with patch("app.tools.chroma_out_tool.search", return_value=hits) as mock_search:
        out = tool._run("what to recall", run_manager=run_manager)

    data = json.loads(out)
    assert data == {
        "ok": True,
        "count": 1,
        "hits": [{"id": "id1", "text": "doc1", "metadata": {"user_id": "u1"}}],
    }
    mock_search.assert_called_once_with(
        "what to recall",
        k=3,
        where={"user_id": "u1"},
    )


def test_chroma_out_tool_returns_error_payload_on_failure():
    tool = ChromaOutTool()
    with patch("app.tools.chroma_out_tool.search", side_effect=RuntimeError("down")):
        out = tool._run("what to recall", run_manager=None)
    data = json.loads(out)
    assert data["ok"] is False
    assert "down" in data["error"]
