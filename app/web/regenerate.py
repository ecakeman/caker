from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES, RemoveMessage

from app.runtime.graph import get_graph
from app.runtime.state import GraphState


class RegenerateError(Exception):
    pass


def find_regenerate_slice(
    messages: list[dict[str, Any]],
    from_assistant_index: int,
) -> tuple[list[dict[str, Any]], str, int]:
    if from_assistant_index < 0 or from_assistant_index >= len(messages):
        raise RegenerateError("from_assistant_index out of range")
    if messages[from_assistant_index].get("role") != "assistant":
        raise RegenerateError("index must point to an assistant message")

    user_index = -1
    regenerate_input = ""
    for i in range(from_assistant_index - 1, -1, -1):
        if messages[i].get("role") == "user":
            user_index = i
            regenerate_input = str(messages[i].get("content") or "")
            break
    if user_index < 0:
        raise RegenerateError("no preceding user message")

    truncated = messages[: user_index + 1]
    return truncated, regenerate_input, user_index


def web_messages_to_langchain(messages: list[dict[str, Any]]) -> list[BaseMessage]:
    out: list[BaseMessage] = []
    for m in messages:
        role = m.get("role")
        content = str(m.get("content") or "")
        if role == "user":
            out.append(HumanMessage(content=content))
        elif role == "assistant":
            out.append(AIMessage(content=content))
    return out


async def sync_checkpoint_after_regenerate(
    *,
    user_id: str,
    session_id: str,
    truncated_web_messages: list[dict[str, Any]],
) -> None:
    lc_messages = web_messages_to_langchain(truncated_web_messages)
    config = {
        "configurable": {
            "session_id": session_id,
            "thread_id": session_id,
            "user_id": user_id,
        },
    }
    graph = get_graph()
    update: GraphState = {
        "messages": [
            RemoveMessage(id=REMOVE_ALL_MESSAGES),
            *lc_messages,
        ],
        "input": "",
        "result": "",
        "skip_inject_system": True,
        "skip_inject_user": True,
        "result_set_handled": False,
        "streaming": False,
        "sandbox_context": "",
    }
    await graph.aupdate_state(config, update)
