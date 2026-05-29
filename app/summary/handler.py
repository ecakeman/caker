from __future__ import annotations

import tiktoken
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.config import settings
from app.runtime.llm import get_llm

ENCODING = tiktoken.get_encoding("cl100k_base")

COMPACT_PROMPT = (
    "将以下对话历史压缩为简短中文要点，供助手内部参考。"
    "要求：每条一行、最多 15 条、不要标题、不要写工具名、不要写 [SUMMARY] 或 [CONTEXT] 字样。\n\n"
    "{dialog}"
)

_CONTEXT_PREFIX = "[CONTEXT]"
_LEGACY_SUMMARY_PREFIX = "[SUMMARY]"


def _message_text(msg: BaseMessage) -> str:
    content = msg.content
    if isinstance(content, str):
        return content
    return str(content)


def _message_label(msg: BaseMessage) -> str:
    if isinstance(msg, HumanMessage):
        return "human"
    if isinstance(msg, AIMessage):
        return "ai"
    if isinstance(msg, SystemMessage):
        return "system"
    if isinstance(msg, ToolMessage):
        return f"tool:{msg.name or 'unknown'}"
    return msg.__class__.__name__


def estimate_tokens(messages: list[BaseMessage]) -> int:
    total = 0
    for msg in messages:
        total += len(ENCODING.encode(_message_text(msg)))
    return total


def need_compact(messages: list[BaseMessage]) -> bool:
    threshold = int(settings.max_input_tokens * settings.compact_ratio)
    return estimate_tokens(messages) >= threshold


def _is_context_system(msg: BaseMessage) -> bool:
    text = _message_text(msg)
    if not text.startswith(_CONTEXT_PREFIX) and not text.startswith(_LEGACY_SUMMARY_PREFIX):
        return False
    # Legacy compact stored context as SystemMessage; treat as compressible middle.
    return isinstance(msg, (SystemMessage, HumanMessage))


def _context_message(summary_text: str) -> HumanMessage:
    """Store compacted history as HumanMessage (some LLM gateways allow only one SystemMessage)."""
    return HumanMessage(content=f"{_CONTEXT_PREFIX}\n{summary_text}")


def _find_turn_start(messages: list[BaseMessage], current_input: str) -> int:
    target = current_input.strip()
    if target:
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if isinstance(msg, HumanMessage) and _message_text(msg).strip() == target:
                return i
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return i
    return 0


def partition_for_compact(
    messages: list[BaseMessage],
    current_input: str,
) -> tuple[SystemMessage | None, list[BaseMessage], list[BaseMessage]]:
    """Return (primary_system, middle_to_compress, current_turn_tail)."""
    if not messages:
        return None, [], []

    turn_start = _find_turn_start(messages, current_input)
    before_turn = messages[:turn_start]
    current_turn = messages[turn_start:]

    primary_system: SystemMessage | None = None
    middle: list[BaseMessage] = []

    for msg in before_turn:
        if isinstance(msg, SystemMessage) and not _is_context_system(msg):
            if primary_system is None:
                primary_system = msg
            else:
                middle.append(msg)
        else:
            middle.append(msg)

    return primary_system, middle, current_turn


def summarize_messages(messages: list[BaseMessage], *, user_id: str | None = None) -> str:
    if not messages:
        return ""
    dialog = "\n".join(
        f"[{_message_label(m)}] {_message_text(m)}" for m in messages
    )
    out = get_llm(user_id).invoke([HumanMessage(content=COMPACT_PROMPT.format(dialog=dialog))])
    text = out.content if isinstance(out.content, str) else str(out.content)
    return text.strip()


def build_compact_messages(
    messages: list[BaseMessage],
    current_input: str,
    *,
    user_id: str | None = None,
) -> list[BaseMessage]:
    primary_system, middle, current_turn = partition_for_compact(messages, current_input)
    rebuilt: list[BaseMessage] = []
    if primary_system is not None:
        rebuilt.append(primary_system)
    if middle:
        summary_text = summarize_messages(middle, user_id=user_id)
        if summary_text:
            rebuilt.append(_context_message(summary_text))
    rebuilt.extend(current_turn)
    return rebuilt


def sanitize_messages_for_llm(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Some gateways (e.g. Qwen on PAI-EAS) allow only one leading SystemMessage."""
    out: list[BaseMessage] = []
    primary_system_used = False
    for msg in messages:
        if isinstance(msg, SystemMessage):
            text = _message_text(msg)
            if (
                primary_system_used
                or text.startswith(_CONTEXT_PREFIX)
                or text.startswith(_LEGACY_SUMMARY_PREFIX)
            ):
                out.append(HumanMessage(content=text))
            else:
                out.append(msg)
                primary_system_used = True
        else:
            out.append(msg)
    return out


# Backward-compatible aliases for tests migrating from summary naming
need_summary = need_compact


def summarize(messages: list[BaseMessage]) -> SystemMessage:
    text = summarize_messages(messages)
    return SystemMessage(content=f"{_CONTEXT_PREFIX}\n{text}")
