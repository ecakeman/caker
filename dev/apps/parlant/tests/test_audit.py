from __future__ import annotations

from pathlib import Path

from data_pipeline.audit import run_audit


def test_audit_raw_data() -> None:
    root = Path(__file__).resolve().parents[1]
    report = run_audit(
        root / "data/raw/guidelines.json",
        root / "data/raw/journeys.json",
    )
    assert report["guideline_count"] == 182
    assert report["journey_count"] == 6
    assert "tool_distribution" in report
    assert "data_baseline" in report
    assert "similar_guideline_pairs" in report
