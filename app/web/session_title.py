from __future__ import annotations

import re

from langchain_core.messages import HumanMessage

from app.runtime.llm import get_llm

DEFAULT_SESSION_TITLE = "新对话"

_TITLE_PROMPT = (
    "根据以下对话，生成一条用于聊天列表的简短中文标题。\n"
    "要求：不超过18个字；概括对话主题；不要引号；不要句号/问号/叹号结尾；"
    "不要写「标题」前缀；不要复述用户原句。\n\n"
    "对话：\n{dialog}"
)

_MAX_SNIPPET = 600


def _strip_attachment_lines(text: str) -> str:
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("[文件]") or s.startswith("[定位]") or s == "[附件]":
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def format_first_exchange_for_title(messages: list[dict]) -> str:
    """Only the first user message and first assistant reply (ChatGPT-style)."""
    user_text: str | None = None
    assistant_text: str | None = None
    for msg in messages:
        role = msg.get("role")
        raw = str(msg.get("content") or "").strip()
        if not raw:
            continue
        body = _strip_attachment_lines(raw)
        if not body:
            continue
        if role == "user" and user_text is None:
            user_text = body[:_MAX_SNIPPET]
        elif role == "assistant" and user_text is not None and assistant_text is None:
            assistant_text = body[:_MAX_SNIPPET]
            break
    if not user_text:
        return ""
    lines = [f"用户: {user_text}"]
    if assistant_text:
        lines.append(f"助手: {assistant_text}")
    return "\n".join(lines)


def format_dialog_for_title(messages: list[dict]) -> str:
    """Backward-compatible alias; only first exchange is used for titles."""
    return format_first_exchange_for_title(messages)


def normalize_title(raw: str) -> str:
    t = (raw or "").strip()
    t = t.strip("\"'“”‘’`")
    t = re.sub(r"^(标题|题目)[：:\s]*", "", t, flags=re.I)
    t = re.sub(r"[\s。．.!?！？…]+$", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return DEFAULT_SESSION_TITLE
    if len(t) > 24:
        return t[:24] + "…"
    return t


def should_generate_title(messages: list[dict]) -> bool:
    """True when first user+assistant exchange has text (ignores title state)."""
    has_user = False
    has_assistant = False
    for msg in messages:
        role = msg.get("role")
        body = _strip_attachment_lines(str(msg.get("content") or ""))
        if not body:
            continue
        if role == "user":
            has_user = True
        elif role == "assistant":
            has_assistant = True
    return has_user and has_assistant


def title_needs_generation(session: dict) -> bool:
    """Generate title once: only while title is still the default placeholder."""
    title = str(session.get("title") or "").strip()
    if title and title != DEFAULT_SESSION_TITLE:
        return False
    return should_generate_title(session.get("messages") or [])


def generate_session_title(messages: list[dict], *, user_id: str | None = None) -> str:
    dialog = format_first_exchange_for_title(messages)
    if not dialog:
        return DEFAULT_SESSION_TITLE
    out = get_llm(user_id).invoke(
        [HumanMessage(content=_TITLE_PROMPT.format(dialog=dialog))]
    )
    text = out.content if isinstance(out.content, str) else str(out.content)
    return normalize_title(text.strip())
