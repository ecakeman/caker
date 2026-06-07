from __future__ import annotations

import json
from pathlib import Path

from app.loaders.glossary import load_glossary
from app.profile import load_profile


def test_profile_and_glossary_data_present() -> None:
    root = Path(__file__).resolve().parents[1]
    profile = load_profile(root)
    assert "卷叔" in profile
    assert len(profile) > 500
    glossary = load_glossary(root)
    assert len(glossary) >= 10
    assert all("name" in item and "description" in item for item in glossary[:5])
