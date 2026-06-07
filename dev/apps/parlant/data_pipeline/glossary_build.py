from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_glossary(glossary_src: Path | None) -> dict[str, Any]:
    terms: list[dict[str, Any]] = []
    if glossary_src and glossary_src.is_file():
        raw = json.loads(glossary_src.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            terms = raw
        elif isinstance(raw, dict) and isinstance(raw.get("terms"), list):
            terms = raw["terms"]
    return {
        "version": "1",
        "terms": terms,
        "stats": {"term_count": len(terms)},
        "runtime_interface": {
            "loader": "app.loaders.glossary.install_glossary",
            "parlant_api": "agent.create_term",
        },
    }


def write_glossary(*, glossary_src: Path | None, out_path: Path) -> dict[str, Any]:
    doc = build_glossary(glossary_src)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"glossary_path": str(out_path), **doc["stats"]}
