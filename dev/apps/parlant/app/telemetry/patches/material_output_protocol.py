from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable

from parlant.core.emission.event_buffer import EventBuffer
from parlant.core.emission.event_publisher import EventPublisher

from app.telemetry.context import get_collector

_PATCH_APPLIED = False
_ORIGINAL_PUBLISHER_EMIT: Callable[..., Any] | None = None
_ORIGINAL_BUFFER_EMIT: Callable[..., Any] | None = None

_MATERIAL_TOKEN_RE = re.compile(r"\[(?:图片|链接|引用):[A-Za-z0-9_\-:.]+\]|\[暂无可用图片\]")
_FABRICATED_IMAGE_PHRASE_RE = re.compile(
    r"(?:刚才)?(?:我)?(?:刚)?(?:给你|发你|发给你)?(?:发了|发送了)?(?:一张|几张|张)?(?:图|图片)"
    r"|刚给你发了[^，。\n]*|刚才给你发了[^，。\n]*|刚发你的[^，。\n]*"
    r"|如下图|下图|这就发给你看看|你看下图|已发送图片|已发图|图发你了|我发给你|刚才发你"
)


def _token_for_tool(rec: dict[str, Any]) -> str | None:
    if not rec.get("success", True):
        return None
    name = str(rec.get("tool_id") or "")
    if name == "send_image" and rec.get("fallback_no_image"):
        return "[暂无可用图片]"
    args = rec.get("input_summary") or {}
    reuse_id = str(args.get("reuse_id") or "").strip()
    if not reuse_id:
        attachment = str(rec.get("attachment_id") or "")
        if ":" in attachment:
            reuse_id = attachment.split(":", 1)[1].strip()
    if not reuse_id:
        return None
    if name == "send_image":
        return f"[图片:{reuse_id}]"
    if name == "send_link":
        return f"[链接:{reuse_id}]"
    if name == "send_quoted_chat":
        return f"[引用:{reuse_id}]"
    return None


def _material_tokens() -> list[str]:
    collector = get_collector()
    if collector is None:
        return []
    records = getattr(collector, "_tool_records", []) or []
    tokens: list[str] = []
    seen: set[str] = set()
    for rec in records:
        if not isinstance(rec, dict):
            continue
        token = _token_for_tool(rec)
        if token and token not in seen:
            tokens.append(token)
            seen.add(token)
    return tokens


def _message_text(data: Any) -> str:
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        return str(data.get("message") or "")
    return ""


def _with_message(data: Any, message: str) -> Any:
    if isinstance(data, str):
        return message
    if isinstance(data, dict):
        updated = dict(data)
        updated["message"] = message
        return updated
    return data


def render_material_protocol(message: str, tokens: list[str] | None = None) -> str:
    tokens = tokens if tokens is not None else _material_tokens()
    text = message or ""
    allowed = set(tokens)
    text = re.sub(
        _MATERIAL_TOKEN_RE,
        lambda m: m.group(0) if m.group(0) in allowed or m.group(0) == "[暂无可用图片]" else "",
        text,
    )
    existing = _MATERIAL_TOKEN_RE.findall(text)
    token_line = " ".join(t for t in tokens if t not in existing)

    # Remove natural-language claims that a material was sent. The token is
    # the only allowed visible proof of a rendered material.
    parts = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    cleaned_parts = []
    for part in parts:
        if _FABRICATED_IMAGE_PHRASE_RE.search(part) and not _MATERIAL_TOKEN_RE.search(part):
            stripped = _FABRICATED_IMAGE_PHRASE_RE.sub("", part)
            stripped = re.sub(r"[，,。；;：:\s]+", " ", stripped).strip()
            if stripped and len(stripped) >= 8:
                cleaned_parts.append(stripped)
            continue
        cleaned_parts.append(part)
    text = "\n\n".join(cleaned_parts).strip()

    if token_line:
        text = f"{token_line}\n\n{text}".strip()
    return text


def _rewrite_data(data: Any) -> Any:
    message = _message_text(data)
    if not message and not _material_tokens():
        return data
    rendered = render_material_protocol(message)
    collector = get_collector()
    if collector is not None:
        collector.set_agent_response(rendered)
    return _with_message(data, rendered)


def apply_material_output_protocol_patch() -> None:
    global _PATCH_APPLIED, _ORIGINAL_PUBLISHER_EMIT, _ORIGINAL_BUFFER_EMIT
    if _PATCH_APPLIED:
        return

    _ORIGINAL_PUBLISHER_EMIT = EventPublisher.emit_message_event
    _ORIGINAL_BUFFER_EMIT = EventBuffer.emit_message_event

    @wraps(_ORIGINAL_PUBLISHER_EMIT)
    async def patched_publisher_emit(self: EventPublisher, *args: Any, **kwargs: Any) -> Any:
        if "data" in kwargs:
            kwargs["data"] = _rewrite_data(kwargs.get("data"))
        elif len(args) >= 2:
            args = (args[0], _rewrite_data(args[1]), *args[2:])
        return await _ORIGINAL_PUBLISHER_EMIT(self, *args, **kwargs)

    @wraps(_ORIGINAL_BUFFER_EMIT)
    async def patched_buffer_emit(self: EventBuffer, *args: Any, **kwargs: Any) -> Any:
        if "data" in kwargs:
            kwargs["data"] = _rewrite_data(kwargs.get("data"))
        elif len(args) >= 2:
            args = (args[0], _rewrite_data(args[1]), *args[2:])
        return await _ORIGINAL_BUFFER_EMIT(self, *args, **kwargs)

    EventPublisher.emit_message_event = patched_publisher_emit  # type: ignore[method-assign]
    EventBuffer.emit_message_event = patched_buffer_emit  # type: ignore[method-assign]
    _PATCH_APPLIED = True
