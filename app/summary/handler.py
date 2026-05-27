from __future__ import annotations

import tiktoken
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.runtime.llm import get_llm

ENCODING = tiktoken.get_encoding("cl100k_base")
MAX_INPUT_TOKENS = 8000
SUMMARY_COND_RATIO = 0.6

SUMMARY_PROMPT = (
    "请把下面对话压缩成保留事实/结论/未完成动作的中文摘要，控制在 400 字内：\n\n{dialog}"
)

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


def need_summary(messages: list[BaseMessage]) -> bool:
    return estimate_tokens(messages) >= int(MAX_INPUT_TOKENS * SUMMARY_COND_RATIO)

def summarize(messages: list[BaseMessage]) -> SystemMessage:
    dialog = "\n".join(
        f"[{_message_label(m)}] {_message_text(m)}" for m in messages
    )
    out = get_llm().invoke([HumanMessage(content=SUMMARY_PROMPT.format(dialog=dialog))])
    text = out.content if isinstance(out.content, str) else str(out.content)
    return SystemMessage(content=f"[SUMMARY]\n{text}")
