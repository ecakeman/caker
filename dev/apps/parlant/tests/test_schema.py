from __future__ import annotations

import json
from pathlib import Path

from data_pipeline.schema import validate_guidelines, validate_journeys


def test_normalized_schema_valid() -> None:
    root = Path(__file__).resolve().parents[1]
    g = json.loads((root / "artifacts/normalized/guidelines.json").read_text(encoding="utf-8"))
    j = json.loads((root / "artifacts/normalized/journeys.json").read_text(encoding="utf-8"))
    assert not validate_guidelines(g)
    assert not validate_journeys(j)
