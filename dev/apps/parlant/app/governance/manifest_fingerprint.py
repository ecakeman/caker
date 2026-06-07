from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_fingerprint(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fp = dict(manifest.get("manifest_fingerprint") or {})
    fp["manifest_sha256"] = file_sha256(manifest_path)
    fp.setdefault("missing_required_artifacts", [])
    fp["path"] = str(manifest_path)
    return fp
