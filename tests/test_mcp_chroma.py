from __future__ import annotations

from unittest.mock import patch

from app.mcp.registry import registry
from app.mcp.types import ToolContext


def test_chroma_in_stores_with_context():
    ctx = ToolContext(user_id="u1", session_id="s1")
    with patch("app.mcp.handlers.chroma_in.add") as mock_add:
        res = registry.call_tool_sync("chroma_in", {"text": "likes cats"}, ctx)
    assert '"ok": true' in res.text
    mock_add.assert_called_once()
    _mid, text, meta = mock_add.call_args[0]
    assert text == "likes cats"
    assert meta["user_id"] == "u1"
    assert meta["session_id"] == "s1"


def test_chroma_out_searches_by_user():
    ctx = ToolContext(user_id="u2", session_id="s9")
    hits = [("id1", "fact", {"user_id": "u2"})]
    with patch("app.mcp.handlers.chroma_out.search", return_value=hits) as mock_search:
        res = registry.call_tool_sync("chroma_out", {"text": "cats"}, ctx)
    assert '"count": 1' in res.text
    mock_search.assert_called_once_with("cats", k=3, where={"user_id": "u2"})
