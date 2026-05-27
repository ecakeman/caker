"""M11 result_set / apply_result_set / route_after_tools."""

from __future__ import annotations

from langchain_core.messages import ToolMessage

from app.runtime.nodes import apply_result_set_node
from app.runtime.routes import route_after_tools


def test_apply_result_set_from_tool_message():
    out = apply_result_set_node(
        {
            "messages": [ToolMessage(content="final answer", name="result_set", tool_call_id="1")],
            "input": "",
            "result": "",
            "skip_inject_system": False,
            "result_set_handled": False,
            "streaming": False,
        },
        None,
    )
    assert out == {"result": "final answer", "result_set_handled": True}


def test_apply_result_set_ignores_other_tools():
    out = apply_result_set_node(
        {
            "messages": [ToolMessage(content="file body", name="Read", tool_call_id="1")],
            "input": "",
            "result": "",
            "skip_inject_system": False,
            "result_set_handled": False,
            "streaming": False,
        },
        None,
    )
    assert out == {}


def test_route_after_tools():
    assert route_after_tools({"result_set_handled": True}) == "end"  # type: ignore[arg-type]
    assert route_after_tools({"result_set_handled": False}) == "llm"  # type: ignore[arg-type]
