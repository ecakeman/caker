from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import parlant.sdk as p


def glossary_path(root: Path) -> Path:
    return (root / "data" / "glossary" / "terms.json").resolve()


def load_glossary(root: Path, *, glossary_doc: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if glossary_doc and isinstance(glossary_doc.get("terms"), list):
        return list(glossary_doc["terms"])
    return list(json.loads(glossary_path(root).read_text(encoding="utf-8")))


async def install_glossary(
    agent: p.Agent,
    root: Path,
    *,
    glossary_doc: dict[str, Any] | None = None,
) -> dict[str, int]:
    import os

    stats = {"installed": 0, "skipped": 0, "deferred": 0}
    max_install = int((os.environ.get("GOVERNANCE_GLOSSARY_BOOTSTRAP_MAX") or "0").strip())
    terms = load_glossary(root, glossary_doc=glossary_doc)
    if max_install <= 0:
        stats["deferred"] = len(terms)
        return stats
    for item in terms[:max_install]:
        name = str(item.get("name") or "").strip()
        description = str(item.get("description") or "").strip()
        synonyms = [str(x).strip() for x in item.get("synonyms") or [] if str(x).strip()]
        if not name or not description:
            stats["skipped"] += 1
            continue
        await agent.create_term(name=name, description=description, synonyms=synonyms)
        stats["installed"] += 1
    return stats
