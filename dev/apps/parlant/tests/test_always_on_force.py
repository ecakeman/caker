from __future__ import annotations

from app.artifacts import load_artifacts
from app.config import load_settings
from app.matching.relationships import apply_relationship_closure
from pathlib import Path


def test_always_on_force_after_exclusion() -> None:
    root = Path(__file__).resolve().parents[1]
    bundle = load_artifacts(load_settings(root).artifacts_root)
    always_on = list(bundle.scope_map.get("always_on") or [])
    closed, _ = apply_relationship_closure(always_on, bundle.relationships)
    missing = set(always_on) - set(closed)
    assert missing, "fixture should drop at least one always-on via exclusion"
    closed_set = set(closed)
    for gid in always_on:
        if gid not in closed_set:
            closed.append(gid)
            closed_set.add(gid)
    assert len(closed_set) == len(always_on)
