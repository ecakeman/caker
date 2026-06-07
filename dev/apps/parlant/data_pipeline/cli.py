from __future__ import annotations

import json
from pathlib import Path

from data_pipeline.audit import run_audit
from data_pipeline.audit_extended import run_extended_audit
from data_pipeline.canned import write_canned
from data_pipeline.env import load_settings
from data_pipeline.fingerprint import write_manifest_fingerprint
from data_pipeline.glossary_build import write_glossary
from data_pipeline.index_build import build_indexes
from data_pipeline.journey_governance import write_journey_artifacts
from data_pipeline.hash_utils import file_sha256
from data_pipeline.manifest import build_manifest, source_hashes, write_manifest
from data_pipeline.migrate import archive_legacy_artifacts
from data_pipeline.normalize import write_normalized
from data_pipeline.relationships import write_relationships
from data_pipeline.retriever_corpus import write_retriever_corpus
from data_pipeline.scope import write_scope_map
from data_pipeline.scenario_expectations import write_scenario_expectations
from data_pipeline.variables import write_variables

PIPELINE_VERSION = "2"


def run_all(root: Path | None = None) -> dict:
    settings = load_settings(root)
    archived = archive_legacy_artifacts(settings.artifacts_root, root=settings.root)
    if archived:
        print(f"[pipeline] archived legacy artifacts -> {archived}")

    artifacts = settings.artifacts_root
    normalized_dir = artifacts / "normalized"
    reports_dir = artifacts / "reports"
    indexes_dir = artifacts / "indexes"
    retriever_dir = artifacts / "retrievers_corpus"
    reports_dir.mkdir(parents=True, exist_ok=True)

    raw_relations = settings.root / "data" / "raw" / "relations.json"
    glossary_src = settings.root / "data" / "glossary" / "terms.json"
    scenarios_src = settings.root / "data" / "sim_scenarios" / "scenarios.json"

    audit = run_audit(settings.raw_guidelines, settings.raw_journeys)
    audit_path = reports_dir / "audit_report.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    norm_info = write_normalized(settings.raw_guidelines, settings.raw_journeys, normalized_dir)
    guidelines_path = normalized_dir / "guidelines.json"
    journeys_path = normalized_dir / "journeys.json"

    scope_info = write_scope_map(guidelines_path, journeys_path, artifacts / "scope_map.json")
    rel_info = write_relationships(
        guidelines_path,
        artifacts / "relationships.json",
        raw_relations_path=raw_relations if raw_relations.is_file() else None,
    )
    var_info = write_variables(guidelines_path, journeys_path, artifacts / "variables.json")
    canned_info = write_canned(guidelines_path, artifacts / "canned_responses.json")
    glossary_info = write_glossary(glossary_src=glossary_src if glossary_src.is_file() else None, out_path=artifacts / "glossary.json")
    corpus_info = write_retriever_corpus(guidelines_path, retriever_dir)
    exp_info = {}
    if scenarios_src.is_file():
        exp_info = write_scenario_expectations(
            scenarios_src,
            settings.root / "data" / "sim_scenarios" / "expectations.json",
            guidelines_path=guidelines_path,
        )

    norm_journeys = json.loads(journeys_path.read_text(encoding="utf-8"))
    gov_info = write_journey_artifacts(norm_journeys, reports_dir / "journeys")
    index_info = build_indexes(
        json.loads(guidelines_path.read_text(encoding="utf-8")),
        embedding_model=settings.embedding_model,
        embedding_base_url=settings.embedding_base_url,
        embedding_api_key=settings.embedding_api_key,
        embedding_dimensions=settings.embedding_dimensions,
        out_dir=indexes_dir,
    )

    extended = run_extended_audit(
        guidelines_path=guidelines_path,
        journeys_path=journeys_path,
        scope_path=artifacts / "scope_map.json",
        relationships_path=artifacts / "relationships.json",
        variables_path=artifacts / "variables.json",
        index_records_path=indexes_dir / "records.jsonl",
        corpus_path=retriever_dir / "corpus.jsonl",
    )
    extended_path = reports_dir / "audit_extended.json"
    extended_path.write_text(json.dumps(extended, ensure_ascii=False, indent=2), encoding="utf-8")

    g_hash, j_hash = source_hashes(settings.raw_guidelines, settings.raw_journeys)
    relationship_cycles_path = reports_dir / "relationship_cycles.json"
    scenario_expectations_path = settings.root / "data" / "sim_scenarios" / "expectations.json"
    paths = {
        "audit_report": audit_path,
        "audit_extended": extended_path,
        "normalized_guidelines": guidelines_path,
        "normalized_journeys": journeys_path,
        "schema_contract": artifacts / "schema_contract.json",
        "scope_map": artifacts / "scope_map.json",
        "relationships": artifacts / "relationships.json",
        "relationship_cycles": relationship_cycles_path,
        "variables": artifacts / "variables.json",
        "canned_responses": artifacts / "canned_responses.json",
        "glossary": artifacts / "glossary.json",
        "scenario_expectations": scenario_expectations_path,
        "journey_governance": reports_dir / "journeys" / "journey_governance.json",
        "journey_mermaid_dir": reports_dir / "journeys" / "mermaid",
        "retriever_corpus": retriever_dir / "corpus.jsonl",
        "retrieval_config": retriever_dir / "retrieval_config.json",
        "index_meta": indexes_dir / "index_meta.json",
        "index_records": indexes_dir / "records.jsonl",
        "index_vectors": indexes_dir / "condition_vectors.npy",
        "index_bm25": indexes_dir / "bm25_corpus.json",
    }
    stats = {
        "pipeline_version": PIPELINE_VERSION,
        "guidelines": norm_info["guideline_count"],
        "journeys": norm_info["journey_count"],
        "archived_legacy": str(archived) if archived else None,
        **scope_info,
        **rel_info,
        **var_info,
        **canned_info,
        **glossary_info,
        **corpus_info,
        **exp_info,
        **gov_info,
        **index_info,
        "audit_extended_path": str(extended_path),
    }
    manifest = build_manifest(
        root=settings.root,
        source={
            "guidelines": str(settings.raw_guidelines),
            "journeys": str(settings.raw_journeys),
            "relations": str(raw_relations) if raw_relations.is_file() else None,
            "glossary": str(glossary_src) if glossary_src.is_file() else None,
            "guidelines_hash": g_hash,
            "journeys_hash": j_hash,
            "relations_hash": file_sha256(raw_relations) if raw_relations.is_file() else None,
        },
        paths=paths,
        stats=stats,
    )
    manifest_path = artifacts / "manifest.json"
    write_manifest(manifest, manifest_path)
    fingerprint = write_manifest_fingerprint(
        manifest_path,
        reports_dir / "manifest_fingerprint.json",
    )
    manifest["manifest_fingerprint"] = {
        "path": "artifacts/reports/manifest_fingerprint.json",
        "manifest_sha256": fingerprint["manifest_sha256"],
        "missing_required_artifacts": fingerprint["missing_required_artifacts"],
    }
    write_manifest(manifest, manifest_path)
    fingerprint = write_manifest_fingerprint(
        manifest_path,
        reports_dir / "manifest_fingerprint.json",
    )
    if fingerprint.get("missing_required_artifacts"):
        raise RuntimeError(
            "missing required artifacts: "
            + ", ".join(fingerprint["missing_required_artifacts"])
        )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


if __name__ == "__main__":
    run_all()
