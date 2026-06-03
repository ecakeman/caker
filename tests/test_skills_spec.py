from __future__ import annotations

from pathlib import Path

import pytest

from app.skills.manager import SkillValidationError, skills_manager, validate_skill_md

SKILLS_ROOT = Path(__file__).resolve().parents[1] / "skills"

EXPECTED_SKILLS = {
    "demo-hello",
    "file-extract",
    "sqlite-query",
    "github-readonly",
    "markdown-report",
    "report-html",
    "deepresearch-lite",
    "online-search-web",
    "memory-remember",
    "memory-recall",
    "caker-introspect",
}


def test_each_skill_directory_valid():
    for name in sorted(EXPECTED_SKILLS):
        fm = validate_skill_md(SKILLS_ROOT / name)
        assert fm["name"] == name


def test_skills_manager_indexes_all_expected():
    skills_manager.reindex()
    indexed = {m["name"] for m in skills_manager.list_meta()}
    assert EXPECTED_SKILLS.issubset(indexed)


def test_hello_skill_removed():
    assert not (SKILLS_ROOT / "hello_skill").is_dir()


def test_invalid_name_rejected(tmp_path):
    bad = tmp_path / "Bad_Name"
    bad.mkdir()
    (bad / "SKILL.md").write_text(
        "---\nname: bad\n description: x\n---\n",
        encoding="utf-8",
    )
    with pytest.raises(SkillValidationError):
        validate_skill_md(bad)
