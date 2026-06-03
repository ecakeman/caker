from __future__ import annotations

import pytest

from app.web.regenerate import (
    RegenerateError,
    find_regenerate_slice,
    web_messages_to_langchain,
)
from langchain_core.messages import AIMessage, HumanMessage


def test_find_regenerate_slice():
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "again"},
        {"role": "assistant", "content": "sure"},
    ]
    truncated, regen, idx = find_regenerate_slice(messages, 3)
    assert idx == 2
    assert regen == "again"
    assert len(truncated) == 3
    assert truncated[-1]["role"] == "user"


def test_find_regenerate_slice_requires_assistant():
    messages = [{"role": "user", "content": "x"}]
    with pytest.raises(RegenerateError):
        find_regenerate_slice(messages, 0)


def test_web_messages_to_langchain():
    lc = web_messages_to_langchain(
        [
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
        ]
    )
    assert isinstance(lc[0], HumanMessage)
    assert isinstance(lc[1], AIMessage)


def test_sync_checkpoint_after_regenerate(monkeypatch):
    import asyncio

    from app.web import regenerate as reg_mod

    calls = []

    class FakeGraph:
        async def aupdate_state(self, config, update):
            calls.append((config, update))

    monkeypatch.setattr(reg_mod, "get_graph", lambda: FakeGraph())

    asyncio.run(
        reg_mod.sync_checkpoint_after_regenerate(
            user_id="u1",
            session_id="s1",
            truncated_web_messages=[{"role": "user", "content": "hi"}],
        )
    )
    assert len(calls) == 1
    _config, update = calls[0]
    assert update["skip_inject_user"] is True
    assert update["skip_inject_system"] is True
    assert len(update["messages"]) == 2
