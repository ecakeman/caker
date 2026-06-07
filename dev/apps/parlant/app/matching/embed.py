from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Sequence

from openai import AsyncOpenAI

_EMBED_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="embed-sync")


async def embed_query(
    text: str,
    *,
    model: str,
    base_url: str,
    api_key: str,
    dimensions: int,
) -> list[float]:
    client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=60.0)
    try:
        resp = await client.embeddings.create(
            model=model.removeprefix("openai/"),
            input=[text],
            dimensions=dimensions,
            encoding_format="float",
        )
        return resp.data[0].embedding
    finally:
        await client.close()


def embed_query_sync(
    text: str,
    *,
    model: str,
    base_url: str,
    api_key: str,
    dimensions: int,
) -> list[float]:
    """Sync wrapper safe inside Parlant gateway event loop (no nested asyncio.run)."""

    def _run() -> list[float]:
        return asyncio.run(
            embed_query(
                text,
                model=model,
                base_url=base_url,
                api_key=api_key,
                dimensions=dimensions,
            )
        )

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _run()
    return _EMBED_EXECUTOR.submit(_run).result()
