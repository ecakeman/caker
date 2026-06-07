from __future__ import annotations

import asyncio
import os
from typing import Any, Mapping

import httpx
from openai import AsyncOpenAI
from parlant.adapters.nlp.litellm_service import LiteLLMEmbedder, LiteLLMService
from parlant.core.loggers import Logger
from parlant.core.meter import Meter
from parlant.core.nlp.embedding import Embedder, EmbeddingResult
from parlant.core.nlp.service import NLPService
from parlant.core.tracer import Tracer
import parlant.sdk as p

_REGISTERED: set["ConfiguredEmbedder"] = set()


class ConfiguredEmbedder(LiteLLMEmbedder):
    def __init__(
        self,
        model_name: str,
        logger: Logger,
        tracer: Tracer,
        meter: Meter,
        base_url: str | None = None,
    ) -> None:
        super().__init__(model_name, logger, tracer, meter, base_url)
        timeout = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=30.0)
        self._batch_limit = int(os.environ.get("PARLANT_EMBEDDING_BATCH_LIMIT", "10"))
        self._sem = asyncio.Semaphore(int(os.environ.get("PARLANT_EMBEDDING_CONCURRENCY", "4")))
        self._client = AsyncOpenAI(
            api_key=os.environ["EMBEDDING_API_KEY"],
            base_url=os.environ["EMBEDDING_BASE_URL"],
            timeout=timeout,
        )
        _REGISTERED.add(self)

    async def do_embed(self, texts: list[str], hints: Mapping[str, Any] = {}) -> EmbeddingResult:
        model = self.model_name.removeprefix("openai/")
        dims = int(os.environ.get("EMBEDDING_DIMENSIONS", "1024"))
        if len(texts) <= self._batch_limit:
            resp = await self._client.embeddings.create(
                model=model, input=texts, dimensions=dims, encoding_format="float"
            )
            return EmbeddingResult(vectors=[d.embedding for d in resp.data])

        async def one_batch(chunk: list[str]) -> list[list[float]]:
            async with self._sem:
                resp = await self._client.embeddings.create(
                    model=model, input=chunk, dimensions=dims, encoding_format="float"
                )
            return [d.embedding for d in resp.data]

        chunks = [texts[i : i + self._batch_limit] for i in range(0, len(texts), self._batch_limit)]
        parts = await asyncio.gather(*(one_batch(c) for c in chunks))
        vectors: list[list[float]] = []
        for part in parts:
            vectors.extend(part)
        return EmbeddingResult(vectors=vectors)


class ConfiguredLiteLLMService(LiteLLMService):
    def create_embedder(self) -> Embedder:
        return ConfiguredEmbedder(
            model_name=os.environ["EMBEDDING_MODEL_NAME"],
            logger=self.logger,
            tracer=self._tracer,
            meter=self._meter,
            base_url=os.environ.get("EMBEDDING_BASE_URL"),
        )


def nlp_service_factory(container: Any) -> NLPService:
    if error := LiteLLMService.verify_environment():
        raise p.NLPServiceConfigurationError(error)
    service = ConfiguredLiteLLMService(container[p.Logger], container[p.Tracer], container[p.Meter])
    embedder = service.create_embedder()
    container[type(embedder)] = embedder
    return service


async def close_embedders() -> None:
    for emb in list(_REGISTERED):
        try:
            await emb._client.close()
        except Exception:
            pass
    _REGISTERED.clear()
