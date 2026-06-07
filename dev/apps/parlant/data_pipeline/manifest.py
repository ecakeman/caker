from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data_pipeline.hash_utils import artifact_entry, file_sha256

PIPELINE_VERSION = "2"


def build_manifest(
    *,
    root: Path,
    source: dict[str, Any],
    paths: dict[str, Path],
    stats: dict[str, Any],
) -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    for key, path in paths.items():
        if path.is_file():
            artifacts[key] = artifact_entry(path, root=root)
        elif path.is_dir():
            artifacts[key] = artifact_entry(path, root=root)
    return {
        "version": "2",
        "pipeline_version": PIPELINE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "paths": {k: str(p.resolve().relative_to(root.resolve())) for k, p in paths.items()},
        "artifacts": artifacts,
        "stats": stats,
    }


def write_manifest(manifest: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def source_hashes(guidelines_path: Path, journeys_path: Path) -> tuple[str, str]:
    return file_sha256(guidelines_path), file_sha256(journeys_path)
