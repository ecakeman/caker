from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def archive_legacy_artifacts(artifacts_root: Path, *, root: Path) -> Path | None:
    """Move pre-v2 artifacts tree to deprecated/ before regenerating."""
    manifest_path = artifacts_root / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    version = str(manifest.get("pipeline_version") or manifest.get("version") or "1")
    if version == "2":
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = root / "deprecated" / f"artifacts_v{version}_{stamp}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if artifacts_root.exists():
        shutil.move(str(artifacts_root), str(dest))
    artifacts_root.mkdir(parents=True, exist_ok=True)
    return dest
