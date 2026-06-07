from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Any, Callable

from parlant.adapters.nlp.litellm_service import LiteLLMSchematicGenerator

from app.telemetry.context import get_collector

_logger = logging.getLogger(__name__)
_PATCH_APPLIED = False
_ORIGINAL: Callable[..., Any] | None = None


def _stage_from_schema(schema_name: str) -> str:
    name = (schema_name or "").lower()
    if "guideline" in name or "match" in name:
        return "judge_match"
    if "message" in name or "draft" in name or "response" in name:
        return "compose"
    if "tool" in name:
        return "tools"
    return "other"


def apply_litellm_telemetry_patch() -> None:
    global _PATCH_APPLIED, _ORIGINAL
    if _PATCH_APPLIED:
        return
    _ORIGINAL = LiteLLMSchematicGenerator.do_generate

    @wraps(_ORIGINAL)
    async def patched_do_generate(self: LiteLLMSchematicGenerator, prompt: Any, hints: Any = {}) -> Any:
        assert _ORIGINAL is not None
        schema_name = getattr(getattr(self, "schema", None), "__name__", "unknown")
        stage = _stage_from_schema(schema_name)
        t0 = time.perf_counter()
        error: str | None = None
        result: Any = None
        try:
            result = await _ORIGINAL(self, prompt, hints)
            return result
        except Exception as exc:
            error = type(exc).__name__
            raise
        finally:
            collector = get_collector()
            if collector is not None:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                prompt_tokens = 0
                completion_tokens = 0
                model = getattr(self, "id", None) or getattr(self, "model_name", "unknown")
                if result is not None:
                    info = getattr(result, "info", None)
                    usage = getattr(info, "usage", None) if info else None
                    if usage:
                        prompt_tokens = int(getattr(usage, "input_tokens", 0) or 0)
                        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
                collector.record_llm_call(
                    stage=stage,
                    schema_name=schema_name,
                    model=str(model),
                    latency_ms=latency_ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    error=error,
                )

    LiteLLMSchematicGenerator.do_generate = patched_do_generate  # type: ignore[method-assign]
    _PATCH_APPLIED = True
    _logger.info("telemetry: patched LiteLLMSchematicGenerator.do_generate")
