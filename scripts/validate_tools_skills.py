#!/usr/bin/env python3
"""Validate MCP tools and Agent Skills compliance."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.mcp.registry import registry  # noqa: E402
from app.skills.manager import SkillValidationError, skills_manager, validate_skill_md  # noqa: E402


def main() -> int:
    errors: list[str] = []

    print("MCP tools:")
    for t in registry.list_tools_public(include_result_set=True):
        schema = t["inputSchema"]
        if schema.get("type") != "object":
            errors.append(f"tool {t['name']}: inputSchema.type must be object")
        print(f"  - {t['name']}")

    skills_root = ROOT / "skills"
    print("\nSkills:")
    for child in sorted(skills_root.iterdir()):
        if not child.is_dir():
            continue
        try:
            fm = validate_skill_md(child)
            print(f"  - {fm.get('name', child.name)}")
        except SkillValidationError as e:
            errors.append(str(e))
            print(f"  - INVALID {child.name}: {e}")

    skills_manager.reindex()
    indexed = {m["name"] for m in skills_manager.list_meta()}
    required = {
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
    chroma = {"chroma_in", "chroma_out"}
    tool_names = {t["name"] for t in registry.list_tools_public(include_result_set=False)}
    if not chroma.issubset(tool_names):
        errors.append(f"missing chroma tools: {sorted(chroma - tool_names)}")
    missing = required - indexed
    if missing:
        errors.append(f"missing indexed skills: {sorted(missing)}")

    if errors:
        print("\nFAILED:")
        for e in errors:
            print(f"  {e}")
        return 1

    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
