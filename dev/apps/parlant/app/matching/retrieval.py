from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
from rank_bm25 import BM25Okapi

from app.matching.embed import embed_query_sync


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[\u4e00-\u9fff]{1,}|[a-zA-Z0-9_]+", text.lower())


def _rrf(rank_lists: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranks in rank_lists:
        for i, gid in enumerate(ranks):
            scores[gid] = scores.get(gid, 0.0) + 1.0 / (k + i + 1)
    return scores


class GuidelineIndex:
    def __init__(self, root: Path, index_meta: dict[str, Any]) -> None:
        index_dir = root / "artifacts" / "indexes"
        bm25_data = json.loads((index_dir / index_meta["bm25_path"]).read_text(encoding="utf-8"))
        self.records = bm25_data["records"]
        self.bm25 = BM25Okapi(bm25_data["tokenized"])
        self.vectors = np.load(index_dir / index_meta["vector_path"])
        self.id_to_idx = {r["guideline_id"]: i for i, r in enumerate(self.records)}

    def search(
        self,
        query: str,
        *,
        top_k: int,
        rrf_k: int,
        embedding_model: str,
        embedding_base_url: str,
        embedding_api_key: str,
        embedding_dimensions: int,
        extra_queries: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        queries = [query, *(extra_queries or [])]
        all_bm25_ranks: list[list[str]] = []
        all_vec_ranks: list[list[str]] = []
        bm25_top: dict[str, float] = {}
        vec_top: dict[str, float] = {}

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
        norms = np.linalg.norm(self.vectors, axis=1) * (np.linalg.norm(qvec) or 1e-8)
        sims = (self.vectors @ qvec) / np.maximum(norms, 1e-8)

        for q in queries:
            tokens = _tokenize(q)
            bm25_scores = self.bm25.get_scores(tokens)
            bm25_order = np.argsort(bm25_scores)[::-1][: top_k * 3]
            bm25_rank = [self.records[i]["guideline_id"] for i in bm25_order]
            all_bm25_ranks.append(bm25_rank)
            for i in bm25_order[:top_k]:
                gid = self.records[i]["guideline_id"]
                bm25_top[gid] = max(bm25_top.get(gid, 0.0), float(bm25_scores[i]))

        vec_order = np.argsort(sims)[::-1][: top_k * 3]
        vec_rank = [self.records[i]["guideline_id"] for i in vec_order]
        all_vec_ranks.append(vec_rank)
        for i in vec_order[:top_k]:
            gid = self.records[i]["guideline_id"]
            vec_top[gid] = max(vec_top.get(gid, 0.0), float(sims[i]))

        fused = _rrf(all_bm25_ranks + all_vec_ranks, k=rrf_k)
        ordered = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:top_k]
        out: list[dict[str, Any]] = []
        for gid, score in ordered:
            rec = dict(self.records[self.id_to_idx[gid]])
            rec.update({
                "rrf_score": score,
                "bm25_score": bm25_top.get(gid, 0.0),
                "vector_score": vec_top.get(gid, 0.0),
            })
            out.append(rec)
        meta = {
            "query_count": len(queries),
            "bm25_top_ids": list(bm25_rank[:top_k]),
            "vector_top_ids": vec_rank[:top_k],
        }
        return out, meta
