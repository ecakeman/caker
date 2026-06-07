from __future__ import annotations

import asyncio
import os
from typing import Sequence

from openai import AsyncOpenAI


def _client(base_url: str, api_key: str) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=60.0)


async def embed_texts(
    texts: Sequence[str],
    *,
    model: str,
    base_url: str,
    api_key: str,
    dimensions: int,
    batch_size: int = 10,
) -> list[list[float]]:
    client = _client(base_url, api_key)
    model_name = model.removeprefix("openai/")
    vectors: list[list[float]] = []
    try:
        for i in range(0, len(texts), batch_size):
            chunk = list(texts[i : i + batch_size])
            resp = await client.embeddings.create(
                model=model_name,
                input=chunk,
                dimensions=dimensions,
                encoding_format="float",
            )
            vectors.extend([d.embedding for d in resp.data])
    finally:
        await client.close()
    return vectors


def embed_texts_sync(
    texts: Sequence[str],
    *,
    model: str,
    base_url: str,
    api_key: str,
    dimensions: int,
) -> list[list[float]]:
    return asyncio.run(
        embed_texts(
            texts,
            model=model,
            base_url=base_url,
            api_key=api_key,
            dimensions=dimensions,
        )
    )
