"""M14 summary handler and routing."""

from __future__ import annotations

from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.runtime.nodes import summary_node
from app.runtime.routes import route_after_tools
from app.summary.handler import estimate_tokens, need_summary


def test_need_summary_true():
    msgs = [HumanMessage(content="x" * 40000)]
    assert need_summary(msgs) is True


def test_need_summary_false():
    msgs = [HumanMessage(content="short")]
    assert need_summary(msgs) is False


def test_estimate_tokens_positive():
    assert estimate_tokens([HumanMessage(content="hello")]) > 0


def test_route_after_tools_summary_branch():
    long_msgs = [HumanMessage(content="x" * 40000)]
    assert route_after_tools({"result_set_handled": False, "messages": long_msgs}) == "summary"  # type: ignore[arg-type]


def test_route_after_tools_end_when_handled():
    assert route_after_tools({"result_set_handled": True, "messages": []}) == "end"  # type: ignore[arg-type]


def test_summary_node_replaces_messages():
    import asyncio

    async def _run() -> None:
        state = {
            "messages": [HumanMessage(content="old"), AIMessage(content="reply")],
            "input": "current question",
            "result": "",
            "skip_inject_system": False,
            "result_set_handled": False,
            "streaming": False,
        }
        fake_summary = SystemMessage(content="[SUMMARY]\ncompressed")
        with patch("app.runtime.nodes.summarize", return_value=fake_summary):
            out = await summary_node(state, None)
        assert len(out["messages"]) == 3
        assert out["messages"][1] == fake_summary
        assert isinstance(out["messages"][2], HumanMessage)
        assert out["messages"][2].content == "current question"

    asyncio.run(_run())
