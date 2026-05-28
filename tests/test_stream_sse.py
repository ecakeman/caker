"""SSE stream status vs delta separation."""

from __future__ import annotations

from app.api.chat import _langgraph_node, _tool_label_from_event


def test_langgraph_node_from_metadata():
    ev = {"metadata": {"langgraph_node": "llm"}}
    assert _langgraph_node(ev) == "llm"


def test_tool_label_from_data_name():
    ev = {"data": {"name": "read"}}
    assert _tool_label_from_event(ev) == "read"
