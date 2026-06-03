from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.config import settings
from app.observability.llm_meta import (
    accumulate_run_tokens,
    build_llm_invoke_meta,
    extract_token_usage,
    format_ai_completion,
    reset_run_token_totals,
)
from app.observability.session_log import SessionLogContext, _sanitize_meta


def test_extract_token_usage_from_usage_metadata():
    ai = AIMessage(content="hi", usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})
    usage = extract_token_usage(ai)
    assert usage["prompt_tokens"] == 10
    assert usage["completion_tokens"] == 5
    assert usage["total_tokens"] == 15


def test_extract_token_usage_from_response_metadata():
    ai = AIMessage(
        content="hi",
        response_metadata={"token_usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28}},
    )
    usage = extract_token_usage(ai)
    assert usage["prompt_tokens"] == 20
    assert usage["completion_tokens"] == 8


def test_token_fields_not_redacted():
    meta = _sanitize_meta(
        {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "api_key": "sk-secret123456789012345678901234567890",
        }
    )
    assert meta["prompt_tokens"] == 100
    assert meta["completion_tokens"] == 50
    assert meta["api_key"] == "***"


def test_run_token_accumulation():
    reset_run_token_totals("u", "s")
    acc1 = accumulate_run_tokens("u", "s", {"prompt_tokens": 10, "completion_tokens": 5})
    acc2 = accumulate_run_tokens("u", "s", {"prompt_tokens": 3, "completion_tokens": 2})
    assert acc1["run_prompt_tokens"] == 10
    assert acc2["run_prompt_tokens"] == 13
    assert acc2["run_completion_tokens"] == 7
    reset_run_token_totals("u", "s")


def test_preview_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "session_llm_preview_enabled", False)
    ctx = SessionLogContext.from_ids("u1", "s1")
    meta = build_llm_invoke_meta(
        ctx,
        messages=[HumanMessage(content="hello")],
        ai=AIMessage(content="world"),
        elapsed_ms=10,
        model="test-model",
    )
    assert "prompt_preview" not in meta
    assert "completion_preview" not in meta


def test_preview_enabled(monkeypatch):
    monkeypatch.setattr(settings, "session_llm_preview_enabled", True)
    monkeypatch.setattr(settings, "session_llm_preview_max_chars", 500)
    ctx = SessionLogContext.from_ids("u1", "s1")
    meta = build_llm_invoke_meta(
        ctx,
        messages=[SystemMessage(content="sys"), HumanMessage(content="hello")],
        ai=AIMessage(content="world", additional_kwargs={"reasoning_content": "think step"}),
        elapsed_ms=10,
        model="test-model",
    )
    assert "hello" in meta["prompt_preview"]
    assert meta["completion_preview"] == "world"
    assert meta["reasoning_preview"] == "think step"
    assert meta.get("total_tokens", 0) > 0
    assert meta.get("token_source") == "tiktoken_estimate"
    assert "prompt_tokens_estimated" not in meta


def test_reasoning_from_content_blocks(monkeypatch):
    monkeypatch.setattr(settings, "session_llm_preview_enabled", True)
    ctx = SessionLogContext.from_ids("u1", "s1")
    ai = AIMessage(content=[{"type": "reasoning", "text": "chain of thought"}])
    out = format_ai_completion(ctx, ai)
    assert out["reasoning_preview"] == "chain of thought"
