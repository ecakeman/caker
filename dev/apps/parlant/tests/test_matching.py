from __future__ import annotations

from pathlib import Path

from app.artifacts import load_artifacts
from app.config import load_settings
from app.matching.engine import GuidelineMatchingEngine
from app.matching.relationships import apply_relationship_closure


def test_relationship_closure_exclusion() -> None:
    closed, trace = apply_relationship_closure(
        ["a", "b"],
        [{"type": "exclusion", "source_id": "a", "target_id": "b"}],
    )
    assert "b" not in closed
    assert trace


def test_matching_engine_offline() -> None:
    root = Path(__file__).resolve().parents[1]
    if not (root / "artifacts/manifest.json").is_file():
        return
    settings = load_settings(root)
    bundle = load_artifacts(settings.artifacts_root)
    engine = GuidelineMatchingEngine(bundle, settings)
    trace = engine.match("客户咨询重疾险产品对比", use_llm_judge=False)
    assert trace.retrieval
    assert trace.adaptive_k >= settings.matching_top_k
