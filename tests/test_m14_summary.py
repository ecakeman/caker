"""M14 context compaction (soft compact, replaces nuclear summary)."""

from __future__ import annotations

from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.runtime.nodes import compact_node
from app.runtime.routes import route_after_tools
from app.summary.handler import (
    build_compact_messages,
    estimate_tokens,
    need_compact,
    partition_for_compact,
)


_COMPACT_TEST_CHARS = 900_000  # ~112.5K tokens; default threshold ~111K


def test_need_compact_true():
    msgs = [HumanMessage(content="x" * _COMPACT_TEST_CHARS)]
    assert need_compact(msgs) is True


def test_need_compact_false():
    msgs = [HumanMessage(content="short")]
    assert need_compact(msgs) is False


def test_estimate_tokens_positive():
    assert estimate_tokens([HumanMessage(content="hello")]) > 0


def test_route_after_tools_compact_branch():
    long_msgs = [HumanMessage(content="x" * _COMPACT_TEST_CHARS)]
    assert route_after_tools({"result_set_handled": False, "messages": long_msgs}) == "compact"  # type: ignore[arg-type]


def test_route_after_tools_end_when_handled():
    assert route_after_tools({"result_set_handled": True, "messages": []}) == "end"  # type: ignore[arg-type]


def test_partition_keeps_system_and_current_turn():
    system = SystemMessage(content="sys rules")
    old_human = HumanMessage(content="old q")
    old_ai = AIMessage(content="old a")
    current_human = HumanMessage(content="current q")
    tool = ToolMessage(content="file body", tool_call_id="1", name="read")
    messages = [system, old_human, old_ai, current_human, tool]

    primary, middle, current = partition_for_compact(messages, "current q")
    assert primary is system
    assert middle == [old_human, old_ai]
    assert current == [current_human, tool]


def test_build_compact_inserts_context_not_summary_prefix():
    system = SystemMessage(content="sys")
    messages = [
        system,
        HumanMessage(content="old"),
        AIMessage(content="ans"),
        HumanMessage(content="now"),
    ]
    with patch(
        "app.summary.handler.summarize_messages",
        return_value="line one",
    ):
        built = build_compact_messages(messages, "now")
    assert built[0] is system
    assert isinstance(built[1], HumanMessage)
    assert built[1].content.startswith("[CONTEXT]")
    assert "[SUMMARY]" not in built[1].content
    assert built[-1].content == "now"


def test_sanitize_converts_extra_system_to_human():
    from app.summary.handler import sanitize_messages_for_llm

    messages = [
        SystemMessage(content="sys"),
        SystemMessage(content="[CONTEXT]\nold"),
        HumanMessage(content="now"),
    ]
    fixed = sanitize_messages_for_llm(messages)
    assert isinstance(fixed[0], SystemMessage)
    assert isinstance(fixed[1], HumanMessage)
    assert fixed[1].content.startswith("[CONTEXT]")


def test_compact_node_replaces_with_soft_compact():
    import asyncio

    async def _run() -> None:
        state = {
            "messages": [
                SystemMessage(content="sys"),
                HumanMessage(content="old"),
                AIMessage(content="reply"),
                HumanMessage(content="current question"),
            ],
            "input": "current question",
            "result": "",
            "skip_inject_system": False,
            "result_set_handled": False,
            "streaming": False,
        }
        with (
            patch(
                "app.runtime.nodes.build_compact_result",
                return_value=type(
                    "R",
                    (),
                    {
                        "messages": [
                            SystemMessage(content="sys"),
                            HumanMessage(content="[CONTEXT]\nshort"),
                            HumanMessage(content="current question"),
                        ],
                        "summary_text": "short",
                    },
                )(),
            ) as mock_build,
            patch("app.runtime.nodes.persist_compact_summary"),
        ):
            out = await compact_node(state, None)
            mock_build.assert_called_once()
        assert len(out["messages"]) == 4
        assert out["messages"][-1].content == "current question"

    asyncio.run(_run())
