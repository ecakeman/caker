from __future__ import annotations

import json
import logging
import re
from pathlib import Path

FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SKILLS_ROOT = _REPO_ROOT / "skills"

logger = logging.getLogger(__name__)


class SkillValidationError(ValueError):
    pass


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    m = FRONT_MATTER_RE.match(text)
    if m is None:
        return {}, text
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        meta[key.strip()] = val.strip().strip('"').strip("'")
    return meta, text[m.end() :]


def validate_skill_md(skill_dir: Path) -> dict[str, str]:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise SkillValidationError(f"missing SKILL.md: {skill_dir}")

    text = skill_md.read_text(encoding="utf-8", errors="replace")
    fm, _ = _parse_front_matter(text)
    if not fm:
        raise SkillValidationError(f"missing YAML frontmatter: {skill_md}")

    dir_name = skill_dir.name
    name = fm.get("name", "").strip()
    if not name:
        raise SkillValidationError(f"missing name in {skill_md}")
    if name != dir_name:
        raise SkillValidationError(f"name '{name}' must match directory '{dir_name}'")
    if not _SKILL_NAME_RE.fullmatch(name):
        raise SkillValidationError(f"invalid skill name '{name}'")
    if "--" in name or name.startswith("-") or name.endswith("-"):
        raise SkillValidationError(f"invalid skill name hyphens: '{name}'")

    desc = fm.get("description", "").strip()
    if not desc or len(desc) > 1024:
        raise SkillValidationError(f"description must be 1-1024 chars in {skill_md}")

    return fm


class SkillManager:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or _DEFAULT_SKILLS_ROOT).resolve()
        self._index: dict[str, Path] = {}

    def reindex(self) -> None:
        self._index.clear()
        if not self.root.is_dir():
            return
        for child in sorted(self.root.iterdir()):
            if not child.is_dir():
                continue
            skill_md = child / "SKILL.md"
            if not skill_md.is_file():
                continue
            try:
                validate_skill_md(child)
            except SkillValidationError as e:
                logger.warning("skip invalid skill %s: %s", child.name, e)
                continue
            self._index[child.name] = skill_md

    def list_meta(self) -> list[dict[str, str]]:
        metas: list[dict[str, str]] = []
        for name, path in sorted(self._index.items()):
            text = path.read_text(encoding="utf-8", errors="replace")
            fm, _ = _parse_front_matter(text)
            entry: dict[str, str] = {
                "name": fm.get("name", name),
                "description": fm.get("description", ""),
            }
            if fm.get("compatibility"):
                entry["compatibility"] = fm["compatibility"]
            meta_json = fm.get("metadata")
            if meta_json:
                entry["metadata"] = meta_json
            version = fm.get("version")
            if version:
                entry["version"] = version
            metas.append(entry)
        return metas

    def load_body(self, name: str) -> str:
        path = self._index.get(name)
        if path is None:
            self.reindex()
            path = self._index.get(name)
        if path is None:
            raise KeyError(name)
        text = path.read_text(encoding="utf-8", errors="replace")
        _, body = _parse_front_matter(text)
        return body.strip()

    def load_system_prompt(self) -> str:
        path = _REPO_ROOT / "system_prompt.md"
        if not path.is_file():
            raise FileNotFoundError(f"system prompt not found: {path}")
        return path.read_text(encoding="utf-8")

    def render_system_prompt(
        self,
        skills_meta: str | None = None,
        tools_meta: str | None = None,
    ) -> str:
        from app.mcp.registry import registry

        if skills_meta is None:
            skills_meta = json.dumps(self.list_meta(), ensure_ascii=False, indent=2)
        if tools_meta is None:
            tools_meta = registry.summarize_for_prompt(include_result_set=False)

        template = self.load_system_prompt()
        if "{skills_meta}" not in template:
            raise ValueError("system_prompt.md must contain {skills_meta} placeholder")
        if "{tools_meta}" not in template:
            raise ValueError("system_prompt.md must contain {tools_meta} placeholder")

        out = template.replace("{skills_meta}", skills_meta)
        return out.replace("{tools_meta}", tools_meta)


skills_manager = SkillManager()
skills_manager.reindex()
