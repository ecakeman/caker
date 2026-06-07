from __future__ import annotations

from typing import Any

import numpy as np

from app.matching.embed import embed_query_sync


def rerank_candidates(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    embedding_model: str,
    embedding_base_url: str,
    embedding_api_key: str,
    embedding_dimensions: int,
    record_vectors: np.ndarray,
    id_to_idx: dict[str, int],
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    qvec = np.array(
        embed_query_sync(
            query,
            model=embedding_model,
            base_url=embedding_base_url,
            api_key=embedding_api_key,
            dimensions=embedding_dimensions,
        ),
        dtype=np.float32,
    )
    qnorm = np.linalg.norm(qvec) or 1e-8
    scored: list[dict[str, Any]] = []
    for c in candidates:
        gid = c["guideline_id"]
        idx = id_to_idx[gid]
        vec = record_vectors[idx]
        vnorm = np.linalg.norm(vec) or 1e-8
        sim = float(np.dot(vec, qvec) / (vnorm * qnorm))
        rrf = float(c.get("rrf_score") or 0.0)
        scored.append({**c, "rerank_score": 0.6 * sim + 0.4 * rrf, "vector_sim": sim})
    return sorted(scored, key=lambda x: x["rerank_score"], reverse=True)
