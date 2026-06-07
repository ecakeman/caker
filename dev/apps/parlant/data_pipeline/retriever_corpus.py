from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_retriever_corpus(
    guidelines: list[dict[str, Any]],
    *,
    rrf_k: int = 60,
    top_k: int = 5,
    adaptive_k_max: int = 12,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    for g in guidelines:
        emb_text = f"{g['condition_text']}\n{g['action_text']}"
        records.append(
            {
                "guideline_id": g["guideline_id"],
                "condition_text": g["condition_text"],
                "action_text": g["action_text"],
                "embedding_text": emb_text,
                "scope": g.get("scope"),
                "journey_id": g.get("journey_id"),
                "state_id": g.get("state_id"),
                "risk_level": g.get("risk_level"),
                "tools": g.get("tools") or [],
            }
        )
    config = {
        "version": "1",
        "retrieval": {
            "bm25": {"enabled": True, "tokenize": "zh_en_mixed"},
            "vector": {"enabled": True, "field": "condition_text"},
            "fusion": {"method": "rrf", "rrf_k": rrf_k},
            "rerank": {"enabled": True, "blend": "vector_rrf"},
            "top_k_default": top_k,
            "adaptive_k_max": adaptive_k_max,
        },
        "alignment": {
            "embedding_source_field": "embedding_text",
            "must_match_normalized_guideline_id": True,
        },
    }
    return config, records


def write_retriever_corpus(
    guidelines_path: Path,
    out_dir: Path,
    *,
    rrf_k: int = 60,
    top_k: int = 5,
) -> dict[str, Any]:
    guidelines = json.loads(guidelines_path.read_text(encoding="utf-8"))
    config, records = build_retriever_corpus(guidelines, rrf_k=rrf_k, top_k=top_k)
    out_dir.mkdir(parents=True, exist_ok=True)
    corpus_path = out_dir / "corpus.jsonl"
    with corpus_path.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    config_path = out_dir / "retrieval_config.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "retriever_corpus_dir": str(out_dir),
        "corpus_count": len(records),
        "corpus_path": str(corpus_path),
        "retrieval_config_path": str(config_path),
    }
