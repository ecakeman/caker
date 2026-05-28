"""M13 MemPalace injector helpers."""

from __future__ import annotations

import json
from unittest.mock import patch

from langchain_core.messages import HumanMessage

from app.mempalace.injector import build_bootstrap, should_inject


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


