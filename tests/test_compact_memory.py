from __future__ import annotations

from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.mempalace.compact_memory import format_compact_memory_document, persist_compact_summary
from app.runtime.nodes import compact_node
from app.summary.handler import build_compact_result


def test_format_compact_memory_document():
    doc = format_compact_memory_document(
        "line one\nline two",
        user_id="alice",
        session_id="chat-1",
    )
    assert "alice" in doc
    assert "chat-1" in doc
    assert "line one" in doc


def test_persist_compact_summary_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(
        "app.mempalace.compact_memory.settings.mempalace_compact_persist",
        False,
    )
    with patch("app.mempalace.compact_memory.add") as mock_add:
        assert persist_compact_summary("x", user_id="u", session_id="s") is None
        mock_add.assert_not_called()


def test_persist_compact_summary_calls_chroma(monkeypatch):
    monkeypatch.setattr(
        "app.mempalace.compact_memory.settings.mempalace_compact_persist",
        True,
    )
    with patch("app.mempalace.compact_memory.add") as mock_add:
        mid = persist_compact_summary("要点一", user_id="bob", session_id="chat-x")
    assert mid is not None
    mock_add.assert_called_once()
    args = mock_add.call_args[0]
    assert args[0] == mid
    assert "要点一" in args[1]
    assert args[2]["user_id"] == "bob"
    assert args[2]["session_id"] == "chat-x"
    assert args[2]["source"] == "compact"


def test_build_compact_result_exposes_summary_text():
    messages = [
        SystemMessage(content="sys"),
        HumanMessage(content="old"),
        AIMessage(content="ans"),
        HumanMessage(content="now"),
    ]
    with patch(
        "app.summary.handler.summarize_messages",
        return_value="compressed points",
    ):
        built = build_compact_result(messages, "now")
    assert built.summary_text == "compressed points"
    assert len(built.messages) == 3


def test_compact_node_persists_summary():
    import asyncio

    async def _run() -> None:
        state = {
            "messages": [HumanMessage(content="old"), HumanMessage(content="q")],
            "input": "q",
            "result": "",
            "skip_inject_system": False,
            "result_set_handled": False,
            "streaming": False,
        }
        config = {"configurable": {"user_id": "alice", "session_id": "chat-9"}}
        with (
            patch(
                "app.runtime.nodes.build_compact_result",
                return_value=type(
                    "R",
                    (),
                    {
                        "messages": [HumanMessage(content="[CONTEXT]\nx")],
                        "summary_text": "summary body",
                    },
                )(),
            ),
            patch(
                "app.runtime.nodes.persist_compact_summary",
                return_value="mem-1",
            ) as mock_persist,
        ):
            await compact_node(state, config)
        mock_persist.assert_called_once_with(
            "summary body",
            user_id="alice",
            session_id="chat-9",
        )

    asyncio.run(_run())
