#!/usr/bin/env python3
"""Copy canonical broker data (GitHub master) into parlant ``data/`` and rebuild raw inputs."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BROKER = ROOT.parent / "broker"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def export_guidelines(broker_root: Path) -> list[dict]:
    g_dir = broker_root / "data/guidelines"
    global_rows = _read_json(g_dir / "guidelines_global.json")
    per_j = _read_json(g_dir / "guidelines_per_journey.json")
    if not isinstance(global_rows, list):
        raise SystemExit("guidelines_global.json must be a list")
    if not isinstance(per_j, dict):
        raise SystemExit("guidelines_per_journey.json must be an object")

    out: list[dict] = []
    for item in global_rows:
        row = dict(item)
        row.setdefault("parlant_bucket", "global")
        out.append(row)
    for jid, items in per_j.items():
        if not isinstance(items, list):
            continue
        for item in items:
            row = dict(item)
            row["broker_journey_id"] = jid
            row.setdefault("parlant_bucket", "per_journey")
            out.append(row)
    return out


def main() -> int:
    broker_root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_BROKER
    if not broker_root.is_dir():
        raise SystemExit(f"broker root not found: {broker_root}")

    data = ROOT / "data"
    raw = data / "raw"
    raw.mkdir(parents=True, exist_ok=True)

    guidelines = export_guidelines(broker_root)
    journeys = _read_json(broker_root / "data/journeys/journeys.json")

    (raw / "guidelines.json").write_text(
        json.dumps(guidelines, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (raw / "journeys.json").write_text(
        json.dumps(journeys, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    pairs = [
        (broker_root / "data/profile/agent.md", data / "profile/agent.md"),
        (broker_root / "data/glossary/terms.json", data / "glossary/terms.json"),
        (broker_root / "data/sim_scenarios/scenarios.json", data / "sim_scenarios/scenarios.json"),
    ]
    for src, dst in pairs:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    rel_src = broker_root / "data/guidelines/relations.json"
    if rel_src.is_file():
        shutil.copy2(rel_src, data / "raw/relations.json")

    print(
        json.dumps(
            {
                "broker_root": str(broker_root),
                "guidelines": len(guidelines),
                "journeys": len(journeys),
                "profile": str(data / "profile/agent.md"),
                "glossary_terms": len(_read_json(data / "glossary/terms.json")),
                "scenarios": len(_read_json(data / "sim_scenarios/scenarios.json")),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
