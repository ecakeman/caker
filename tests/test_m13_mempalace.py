"""M13 MemPalace injector and routing."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.mempalace.injector import build_bootstrap, should_inject
from app.runtime.nodes import mempalace_inject_node


def test_should_inject_true_when_last_is_human():
    assert should_inject([HumanMessage(content="hi")]) is True


def test_should_inject_false_when_mempalace_already_injected():
    msgs = [
        HumanMessage(content='{"mempalace": true}'),
        HumanMessage(content="real question"),
    ]
    assert should_inject(msgs) is False


def test_build_bootstrap_returns_json_human_message():
    with patch(
        "app.mempalace.injector.chroma_store.search",
        return_value=[("id1", "cat is gray", {"user_id": "u1"})],
    ):
        msg = build_bootstrap("cat color?", "u1")
    assert msg is not None
    data = json.loads(msg.content)
    assert data["mempalace"] is True
    assert len(data["recall"]) == 1


def test_mempalace_inject_node_no_hits():
    async def _run() -> None:
        state = {
            "messages": [HumanMessage(content="q")],
            "input": "q",
            "result": "",
            "skip_inject_system": False,
            "result_set_handled": False,
            "streaming": False,
        }
        with patch("app.runtime.nodes.build_bootstrap", return_value=None):
            out = await mempalace_inject_node(state, {"configurable": {"user_id": "u1"}})
        assert out == {}

    asyncio.run(_run())


def test_mempalace_inject_node_with_bootstrap():
    async def _run() -> None:
        boot = HumanMessage(content='{"mempalace": true}')
        state = {
            "messages": [HumanMessage(content="q")],
            "input": "q",
            "result": "",
            "skip_inject_system": False,
            "result_set_handled": False,
            "streaming": False,
        }
        with patch("app.runtime.nodes.build_bootstrap", return_value=boot):
            out = await mempalace_inject_node(state, {"configurable": {"user_id": "u1"}})
        assert out == {"messages": [boot]}

    asyncio.run(_run())
