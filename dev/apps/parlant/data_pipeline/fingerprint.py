from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from data_pipeline.hash_utils import file_sha256

KEY_ARTIFACTS = (
    "normalized_guidelines",
    "normalized_journeys",
    "scope_map",
    "relationships",
    "variables",
    "glossary",
    "canned_responses",
    "scenario_expectations",
    "retriever_corpus",
    "retrieval_config",
    "index_meta",
    "index_records",
    "index_vectors",
    "index_bm25",
)


def build_manifest_fingerprint(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts") or {}
    rows: dict[str, Any] = {}
    missing: list[str] = []
    for key in KEY_ARTIFACTS:
        entry = artifacts.get(key)
        if not entry or not entry.get("path") or not entry.get("sha256"):
            missing.append(key)
            continue
        rows[key] = {
            "path": entry.get("path"),
            "sha256": entry.get("sha256"),
            "bytes": entry.get("bytes"),
        }
    source = manifest.get("source") or {}
    return {
        "manifest_path": str(manifest_path),
        "manifest_sha256": file_sha256(manifest_path),
        "pipeline_version": manifest.get("pipeline_version"),
        "generated_at": manifest.get("generated_at"),
        "source_hashes": {
            "guidelines_hash": source.get("guidelines_hash"),
            "journeys_hash": source.get("journeys_hash"),
            "relations_hash": source.get("relations_hash"),
        },
        "artifacts": rows,
        "missing_required_artifacts": missing,
        "index_rebuild_proof": {
            "normalized_guidelines_sha256": rows.get("normalized_guidelines", {}).get("sha256"),
            "retriever_corpus_sha256": rows.get("retriever_corpus", {}).get("sha256"),
            "index_records_sha256": rows.get("index_records", {}).get("sha256"),
            "index_vectors_sha256": rows.get("index_vectors", {}).get("sha256"),
            "index_bm25_sha256": rows.get("index_bm25", {}).get("sha256"),
        },
        "stats": manifest.get("stats") or {},
    }


def write_manifest_fingerprint(manifest_path: Path, out_path: Path) -> dict[str, Any]:
    doc = build_manifest_fingerprint(manifest_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc
