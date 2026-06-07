from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ArtifactBundle:
    root: Path
    manifest: dict[str, Any]
    guidelines: list[dict[str, Any]]
    journeys: list[dict[str, Any]]
    scope_map: dict[str, Any]
    relationships: list[dict[str, Any]]
    variables: dict[str, Any]
    canned_responses: dict[str, Any]
    glossary: dict[str, Any]
    retrieval_config: dict[str, Any]
    index_meta: dict[str, Any]
    index_records: list[dict[str, Any]]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(root: Path, rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else (root / p).resolve()


def _require_manifest_v2(manifest: dict[str, Any], manifest_path: Path) -> None:
    version = str(manifest.get("pipeline_version") or manifest.get("version") or "")
    if version != "2":
        raise RuntimeError(
            f"Artifact manifest at {manifest_path} is version {version!r}; "
            "run: bash scripts/run_pipeline.sh to regenerate pipeline v2 artifacts."
        )


def load_artifacts(artifacts_root: Path) -> ArtifactBundle:
    artifacts_root = artifacts_root.resolve()
    manifest_path = artifacts_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Missing {manifest_path}. Run: bash scripts/run_pipeline.sh"
        )
    manifest = _read_json(manifest_path)
    _require_manifest_v2(manifest, manifest_path)
    paths = manifest["paths"]
    root = artifacts_root.parent

    guidelines = _read_json(_resolve(root, paths["normalized_guidelines"]))
    journeys = _read_json(_resolve(root, paths["normalized_journeys"]))
    scope_map = _read_json(_resolve(root, paths["scope_map"]))
    relationships = _read_json(_resolve(root, paths["relationships"]))
    variables = _read_json(_resolve(root, paths["variables"]))
    canned_responses = _read_json(_resolve(root, paths["canned_responses"]))
    glossary = _read_json(_resolve(root, paths["glossary"]))
    retrieval_config = _read_json(_resolve(root, paths["retrieval_config"]))
    index_meta = _read_json(_resolve(root, paths["index_meta"]))
    records_path = _resolve(root, paths["index_records"])
    index_records = [
        json.loads(line)
        for line in records_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return ArtifactBundle(
        root=root,
        manifest=manifest,
        guidelines=guidelines,
        journeys=journeys,
        scope_map=scope_map,
        relationships=relationships,
        variables=variables,
        canned_responses=canned_responses,
        glossary=glossary,
        retrieval_config=retrieval_config,
        index_meta=index_meta,
        index_records=index_records,
    )
