#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_pipeline.fingerprint import build_manifest_fingerprint  # noqa: E402


def main() -> None:
    manifest_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "artifacts" / "manifest.json"
    doc = build_manifest_fingerprint(manifest_path)
    print(f"[manifest] path={doc['manifest_path']}")
    print(f"[manifest] sha256={doc['manifest_sha256']}")
    missing = doc.get("missing_required_artifacts") or []
    print(f"[manifest] missing_required_artifacts={','.join(missing) if missing else 'none'}")
    for key, entry in (doc.get("artifacts") or {}).items():
        print(f"[manifest] artifact {key} path={entry['path']} sha256={entry['sha256']} bytes={entry['bytes']}")
    print("[manifest-json] " + json.dumps(doc, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
