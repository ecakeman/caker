from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import parlant.sdk as p

from app.bootstrap import bootstrap_agent
from app.config import AppSettings
from app.nlp import close_embedders, nlp_service_factory
from app.profile import load_profile
from app.telemetry.install import configure_telemetry_hooks, install_gateway_telemetry

logger = logging.getLogger(__name__)


def _log_level() -> p.LogLevel:
    raw = (os.environ.get("PARLANT_LOG_LEVEL") or "INFO").strip().upper()
    return getattr(p.LogLevel, raw, p.LogLevel.INFO)


def configure_startup_evaluations() -> None:
    if (os.environ.get("PARLANT_SKIP_STARTUP_EVALUATIONS") or "0").strip().lower() not in {
        "1", "true", "yes", "on",
    }:
        return

    async def _skip(server: p.Server) -> None:
        server.logger.info("Skipping Parlant startup evaluations.")
        server._guideline_evaluations.clear()
        server._journey_evaluations.clear()

    p.Server._process_evaluations = _skip


def _perceived_performance_policy() -> p.NullPerceivedPerformancePolicy | p.BasicPerceivedPerformancePolicy | None:
    perf_env = (os.environ.get("PARLANT_PERFORMANCE_POLICY") or "null").strip().lower()
    if perf_env == "null":
        return p.NullPerceivedPerformancePolicy()
    if perf_env == "basic":
        return p.BasicPerceivedPerformancePolicy()
    raise RuntimeError(
        "PARLANT_PERFORMANCE_POLICY must be 'null' (one-shot, no split) or 'basic'; "
        f"got {perf_env!r}"
    )


def _output_mode() -> p.OutputMode:
    raw = (os.environ.get("PARLANT_OUTPUT_MODE") or "block").strip().lower()
    if raw == "stream":
        return p.OutputMode.STREAM
    if raw == "block":
        return p.OutputMode.BLOCK
    raise RuntimeError("PARLANT_OUTPUT_MODE must be 'block' or 'stream'")


def _agent_description(root: Path) -> str:
    base = load_profile(root)[:24000]
    if (os.environ.get("PARLANT_RESPONSE_MODE") or "").strip().lower() in {"one_shot", "oneshot", "single"}:
        suffix = (
            "\n\n【本轮运行模式：一次性答完】\n"
            "每轮客户只问一个问题时，你用一条完整消息回答，不要拆成多条气泡，"
            "不要先发“收到/确实/咱们一起看看”等占位短句。"
            "需要分点时在同一条消息里用换行，但只输出一条气泡。"
        )
        return (base + suffix)[:24000]
    return base


async def run_server(settings: AppSettings) -> None:
    configure_startup_evaluations()
    install_gateway_telemetry(settings)
    try:
        async with p.Server(
            host=settings.host,
            port=settings.port,
            tool_service_port=settings.tool_service_port,
            nlp_service=nlp_service_factory,
            log_level=_log_level(),
            configure_hooks=configure_telemetry_hooks,
        ) as server:
            agent = await server.create_agent(
                name=settings.agent_name[:120],
                description=_agent_description(settings.root),
                max_engine_iterations=int(os.environ.get("PARLANT_MAX_ENGINE_ITERATIONS", "1")),
                perceived_performance_policy=_perceived_performance_policy(),
                output_mode=_output_mode(),
            )
            stats = await bootstrap_agent(agent, settings)
            logger.info("bootstrap completed stats=%s", stats)
            logger.info("gateway UI: http://127.0.0.1:%s/chat", settings.port)
    finally:
        try:
            await close_embedders()
        except Exception:
            logger.exception("close embedders failed")
        try:
            import litellm
            await litellm.close_litellm_async_clients()
        except Exception:
            logger.exception("close litellm failed")


def run(settings: AppSettings) -> None:
    asyncio.run(run_server(settings))
