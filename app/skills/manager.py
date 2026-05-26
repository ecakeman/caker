from __future__ import annotations

import re
from pathlib import Path

FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SKILLS_ROOT = _REPO_ROOT / "skills"

def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    m = FRONT_MATTER_RE.match(text)
    if m is None:
        return {},text
    meta: dict[str,str] = {}
    for line in m.group(1).splitlines():
        line=line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key,val =line.split(":",1)
        meta[key.strip()] = val.strip().strip('"').strip("'")
    return meta,text[m.end() :]

class SkillManager:
    def __init__(self,root: str | Path | None = None) -> None:
        self.root = Path(root or _DEFAULT_SKILLS_ROOT).resolve()
        self._index: dict[str,Path] = {}

    def reindex(self) -> None:
        self._index.clear()
        if not self.root.is_dir():
            return
        for child in sorted(self.root.iterdir()):
            if not child.is_dir():
                continue
            skill_md=child/"SKILL.md"
            if skill_md.is_file():
                self._index[child.name] = skill_md

    def list_meta(self) -> list[dict[str,str]]:
        metas : list[dict[str,str]] = []
        for name,path in sorted(self._index.items()):
            text=path.read_text(encoding="utf-8",errors="replace")
            fm,_= _parse_front_matter(text)
            metas.append(
                {
                    "name":fm.get("name",name),
                    "description":fm.get("description",""),
                    "version":fm.get("version",""),
                }
            )
        return metas

    def load_body(self,name: str) ->str:
        path = self._index.get(name)
        if path is None:
            self.reindex()
            path = self._index.get(name)
        if path is None:
            raise KeyError(name)
        text = path.read_text(encoding="utf-8",errors="replace")
        _,body = _parse_front_matter(text)
        return body.strip()

skills_manager = SkillManager()
skills_manager.reindex()