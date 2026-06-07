from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from rank_bm25 import BM25Okapi

from data_pipeline.embed import embed_texts_sync

EMBEDDING_FIELD = "governance_embedding_text"
EMBEDDING_TEMPLATE_VERSION = "governance_v2_condition_action_tools"


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[\u4e00-\u9fff]{1,}|[a-zA-Z0-9_]+", text.lower())


def _embedding_text(g: dict[str, Any]) -> str:
    tools = ",".join(str(x) for x in (g.get("tools") or [])) or "none"
    markers = ",".join(str(x) for x in (g.get("condition_markers") or [])) or "none"
    return (
        f"condition: {g['condition_text']}\n"
        f"action: {g['action_text']}\n"
        f"scope: {g.get('scope', 'global')}\n"
        f"risk: {g.get('risk_level', 'low')}\n"
        f"tools: {tools}\n"
        f"markers: {markers}"
    )


def build_indexes(
    guidelines: list[dict[str, Any]],
    *,
    embedding_model: str,
    embedding_base_url: str,
    embedding_api_key: str,
    embedding_dimensions: int,
    out_dir: Path,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    embedding_texts: list[str] = []
    action_texts: list[str] = []
    for g in guidelines:
        emb = _embedding_text(g)
        embedding_texts.append(emb)
        action_texts.append(g["action_text"])
        records.append(
            {
                "guideline_id": g["guideline_id"],
                "condition_text": g["condition_text"],
                "action_text": g["action_text"],
                "embedding_text": emb,
                "embedding_field": EMBEDDING_FIELD,
                "embedding_template": EMBEDDING_TEMPLATE_VERSION,
                "scope": g.get("scope", "global"),
                "risk_level": g.get("risk_level", "low"),
                "tools": g.get("tools") or [],
                "is_tool_trigger": bool(g.get("is_tool_trigger")),
                "required_params": g.get("required_params") or [],
            }
        )

    bm25_corpus = [_tokenize(t) for t in embedding_texts]
    bm25 = BM25Okapi(bm25_corpus)
    bm25_path = out_dir / "bm25_corpus.json"
    bm25_path.write_text(
        json.dumps({"tokenized": bm25_corpus, "records": records}, ensure_ascii=False),
        encoding="utf-8",
    )

    vecs = embed_texts_sync(
        embedding_texts,
        model=embedding_model,
        base_url=embedding_base_url,
        api_key=embedding_api_key,
        dimensions=embedding_dimensions,
    )
    vectors = np.array(vecs, dtype=np.float32)
    vec_path = out_dir / "condition_vectors.npy"
    np.save(vec_path, vectors)
    meta_path = out_dir / "index_meta.json"
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": "2",
        "record_count": len(records),
        "embedding_model": embedding_model,
        "embedding_dimensions": embedding_dimensions,
        "embedding_field": EMBEDDING_FIELD,
        "embedding_text_template": EMBEDDING_TEMPLATE_VERSION,
        "embedding_text_template_body": "condition/action/scope/risk/tools/condition_markers",
        "alignment": "1:1_with_normalized_guideline_id",
        "vector_path": vec_path.name,
        "bm25_path": bm25_path.name,
        "records_path": "records.jsonl",
        "rrf_k_default": 60,
        "rerank": {"enabled": True, "method": "vector_rrf_blend"},
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    records_path = out_dir / "records.jsonl"
    with records_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    return {
        "index_dir": str(out_dir),
        "record_count": len(records),
        "bm25_path": str(bm25_path),
        "vector_path": str(vec_path),
        "meta_path": str(meta_path),
        "embedding_field": EMBEDDING_FIELD,
        "embedding_text_template": EMBEDDING_TEMPLATE_VERSION,
    }
