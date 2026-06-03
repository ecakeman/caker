from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from app.mcp.registry import registry
from app.mcp.types import ToolContext
from app.mirror.github import MirrorError, clear_tree_cache_for_tests, mirror_glob, mirror_read


@pytest.fixture(autouse=True)
def _clear_mirror_cache():
    clear_tree_cache_for_tests()
    yield
    clear_tree_cache_for_tests()


def test_mirror_read_rejects_traversal():
    with pytest.raises(MirrorError, match="traversal"):
        mirror_read("../secret")


def test_mirror_read_decodes_github_file():
    content = "line one\nline two\n"
    payload = {
        "type": "file",
        "encoding": "base64",
        "content": base64.b64encode(content.encode()).decode(),
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = payload

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = mock_resp

    with patch("app.mirror.github.httpx.Client", return_value=mock_client):
        result = mirror_read("README.md", limit=50)

    assert "line one" in result.text
    assert "[caker_mirror]" in result.text
    assert "ecakeman/caker" in result.text


def test_mirror_glob_filters_paths():
    tree = {
        "tree": [
            {"type": "blob", "path": "app/main.py"},
            {"type": "blob", "path": "app/mcp/registry.py"},
            {"type": "tree", "path": "web"},
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = tree

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.get.return_value = mock_resp

    with patch("app.mirror.github.httpx.Client", return_value=mock_client):
        out = mirror_glob("app/mcp/*.py", max_results=10)

    assert out["count"] == 1
    assert out["paths"] == ["app/mcp/registry.py"]


def test_mirror_mcp_tools_registered():
    names = {d.name for d in registry.list_definitions()}
    assert "caker_mirror_read" in names
    assert "caker_mirror_glob" in names


def test_mirror_read_tool_mock():
    ctx = ToolContext(user_id="u", session_id="s")
    with patch(
        "app.mcp.handlers.caker_mirror.mirror_read",
        return_value=MagicMock(text="[caker_mirror] ok\n     1|hello"),
    ):
        res = registry.call_tool_sync(
            "caker_mirror_read",
            {"rel_path": "system_prompt.md"},
            ctx,
        )
    assert not res.is_error
    assert "hello" in res.text
