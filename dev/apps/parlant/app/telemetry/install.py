from __future__ import annotations

import logging
import os
from typing import Any

from parlant.core.engines.alpha.engine import AlphaEngine
from parlant.core.engines.alpha.hooks import EngineHooks

from app.artifacts import load_artifacts
from app.config import AppSettings
from app.runtime.matcher_patch import apply_candidate_provider_patch
from app.telemetry.collector import TurnCollector
from app.telemetry.hooks import begin_turn_collector, register_telemetry_hooks
from app.telemetry.patches.litellm import apply_litellm_telemetry_patch
from app.telemetry.patches.material_fast_path import apply_material_fast_path_patch
from app.telemetry.patches.material_output_protocol import apply_material_output_protocol_patch

_logger = logging.getLogger(__name__)
_ENGINE_PATCHED = False
_ORIGINAL_PROCESS: Any = None


def _telemetry_enabled() -> bool:
    return (os.environ.get("PARLANT_TELEMETRY") or "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def install_gateway_telemetry(settings: AppSettings) -> None:
    if not _telemetry_enabled():
        _logger.info("telemetry: disabled (PARLANT_TELEMETRY=0)")
        return
    apply_litellm_telemetry_patch()
    apply_material_fast_path_patch()
    apply_material_output_protocol_patch()
    apply_candidate_provider_patch(settings)
    _patch_alpha_engine_process(settings)


def _patch_alpha_engine_process(settings: AppSettings) -> None:
    global _ENGINE_PATCHED, _ORIGINAL_PROCESS
    if _ENGINE_PATCHED:
        return
    bundle = load_artifacts(settings.artifacts_root)
    _ORIGINAL_PROCESS = AlphaEngine._do_process

    async def patched_do_process(self: AlphaEngine, context: Any) -> None:
        assert _ORIGINAL_PROCESS is not None
        collector = TurnCollector(root=settings.root, bundle=bundle)
        begin_turn_collector(collector)
        try:
            await _ORIGINAL_PROCESS(self, context)
        finally:
            from app.telemetry.context import get_collector, set_collector

            if get_collector() is not None:
                try:
                    collector.finalize(context)
                except Exception:
                    _logger.exception("telemetry: finalize failed")
                set_collector(None)

    AlphaEngine._do_process = patched_do_process  # type: ignore[method-assign]
    _ENGINE_PATCHED = True
    _logger.info(
        "telemetry: patched AlphaEngine._do_process → var/content_record.jsonl "
        "(TELEMETRY_LEVEL=debug → var/turn_pipeline.jsonl)"
    )


async def configure_telemetry_hooks(hooks: EngineHooks) -> EngineHooks:
    if not _telemetry_enabled():
        return hooks
    return register_telemetry_hooks(hooks)
