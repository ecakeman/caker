from __future__ import annotations

import json
import threading
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.config import settings
from app.summary.handler import estimate_tokens
from app.observability.content_store import encode_value, spill_if_large
from app.observability.session_log import SessionLogContext

_run_totals: dict[str, dict[str, int]] = {}
_run_totals_lock = threading.Lock()


def reset_run_token_totals(user_id: str, session_id: str) -> None:
    key = f"{user_id}:{session_id}"
    with _run_totals_lock:
        _run_totals.pop(key, None)


def _run_key(user_id: str, session_id: str) -> str:
    return f"{user_id}:{session_id}"


def _message_text(msg: BaseMessage) -> str:
    content = msg.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text") or block.get("content") or ""
                if text:
                    parts.append(str(text))
        return "\n".join(parts)
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


def extract_token_usage(message: Any) -> dict[str, int]:
    usage: dict[str, int] = {}
    um = getattr(message, "usage_metadata", None)
    if isinstance(um, dict):
        if um.get("input_tokens") is not None:
            usage["prompt_tokens"] = int(um["input_tokens"])
        if um.get("output_tokens") is not None:
            usage["completion_tokens"] = int(um["output_tokens"])
        if um.get("total_tokens") is not None:
            usage["total_tokens"] = int(um["total_tokens"])

    rm = getattr(message, "response_metadata", None) or {}
    if isinstance(rm, dict):
        tu = rm.get("token_usage") or rm.get("usage")
        if isinstance(tu, dict):
            if tu.get("prompt_tokens") is not None:
                usage.setdefault("prompt_tokens", int(tu["prompt_tokens"]))
            if tu.get("completion_tokens") is not None:
                usage.setdefault("completion_tokens", int(tu["completion_tokens"]))
            if tu.get("total_tokens") is not None:
                usage.setdefault("total_tokens", int(tu["total_tokens"]))
            if tu.get("input_tokens") is not None:
                usage.setdefault("prompt_tokens", int(tu["input_tokens"]))
            if tu.get("output_tokens") is not None:
                usage.setdefault("completion_tokens", int(tu["output_tokens"]))

    if "total_tokens" not in usage and "prompt_tokens" in usage and "completion_tokens" in usage:
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    return usage


def accumulate_run_tokens(user_id: str, session_id: str, usage: dict[str, int]) -> dict[str, int]:
    if not usage:
        return {}
    key = _run_key(user_id, session_id)
    with _run_totals_lock:
        acc = _run_totals.setdefault(
            key,
            {"run_prompt_tokens": 0, "run_completion_tokens": 0},
        )
        acc["run_prompt_tokens"] += usage.get("prompt_tokens", 0)
        acc["run_completion_tokens"] += usage.get("completion_tokens", 0)
        return dict(acc)


def format_messages_preview(
    log_ctx: SessionLogContext,
    messages: list[BaseMessage],
    *,
    max_chars: int | None = None,
) -> str | None:
    if not settings.session_llm_preview_enabled:
        return None
    limit = max_chars or settings.session_llm_preview_max_chars
    lines: list[str] = []
    for msg in messages:
        label = _message_label(msg)
        text = _message_text(msg).strip()
        if not text:
            continue
        lines.append(f"[{label}] {text}")
    joined = "\n".join(lines)
    if len(joined) <= limit:
        return joined
    spilled = spill_if_large(log_ctx, joined, label="prompt", preview_len=limit)
    if isinstance(spilled, str):
        return spilled
    return spilled.get("preview")


def _extract_reasoning(ai: AIMessage) -> str | None:
    extra = getattr(ai, "additional_kwargs", None) or {}
    if isinstance(extra, dict):
        rc = extra.get("reasoning_content") or extra.get("reasoning")
        if rc:
            return str(rc).strip()

    content = ai.content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = str(block.get("type") or "").lower()
            if btype in ("reasoning", "thinking"):
                text = block.get("text") or block.get("content") or block.get("reasoning")
                if text:
                    parts.append(str(text))
        if parts:
            return "\n".join(parts).strip()
    return None


def format_ai_completion(
    log_ctx: SessionLogContext,
    ai: AIMessage,
    *,
    max_chars: int | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not settings.session_llm_preview_enabled:
        return out

    limit = max_chars or settings.session_llm_preview_max_chars
    reasoning = _extract_reasoning(ai)
    if reasoning:
        out["reasoning_preview"] = reasoning[:limit] + ("…" if len(reasoning) > limit else "")

    text = _message_text(ai).strip()
    if text:
        if len(text) <= limit:
            out["completion_preview"] = text
        else:
            out["completion_preview"] = text[:limit] + "…"

    tool_calls = getattr(ai, "tool_calls", None) or []
    if tool_calls:
        summaries: list[str] = []
        for tc in tool_calls[:20]:
            name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "tool")
            args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
            if isinstance(args, dict):
                brief = encode_value(log_ctx, args)
                args_s = json.dumps(brief, ensure_ascii=False)
            else:
                args_s = str(args)
            if len(args_s) > 200:
                args_s = args_s[:200] + "…"
            summaries.append(f"{name}({args_s})")
        out["tool_calls_summary"] = "; ".join(summaries)

    return out


def build_llm_invoke_meta(
    log_ctx: SessionLogContext,
    *,
    messages: list[BaseMessage],
    ai: AIMessage,
    elapsed_ms: int,
    model: str | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "elapsed_ms": elapsed_ms,
        "message_count": len(messages),
    }
    if model:
        meta["model"] = model

    usage = extract_token_usage(ai)
    if usage:
        meta.update(usage)
        meta["token_source"] = "provider"
    else:
        prompt_est = estimate_tokens(messages)
        completion_est = estimate_tokens([ai])
        meta["prompt_tokens"] = prompt_est
        meta["completion_tokens"] = completion_est
        meta["total_tokens"] = prompt_est + completion_est
        meta["token_source"] = "tiktoken_estimate"

    preview = format_messages_preview(log_ctx, messages)
    if preview:
        meta["prompt_preview"] = preview
    meta.update(format_ai_completion(log_ctx, ai))
    return meta
