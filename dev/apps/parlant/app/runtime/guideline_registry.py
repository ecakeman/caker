from __future__ import annotations

from typing import Any

from parlant.core.guidelines import Guideline


def _norm(text: str) -> str:
    return " ".join(str(text or "").split())


class GuidelineRegistry:
    """Map Parlant ``Guideline`` objects to artifact ``guideline_id`` via condition+action."""

    def __init__(self, normalized_guidelines: list[dict[str, Any]]) -> None:
        self._by_key: dict[tuple[str, str], str] = {}
        for row in normalized_guidelines:
            key = (_norm(row.get("condition_text") or row.get("condition") or ""), _norm(row.get("action_text") or row.get("action") or ""))
            if key[0] and key[1]:
                self._by_key[key] = str(row["guideline_id"])

    def artifact_id(self, guideline: Guideline) -> str | None:
        key = (_norm(guideline.content.condition), _norm(guideline.content.action))
        return self._by_key.get(key)

    def keys_for_ids(self, artifact_ids: set[str], guidelines: list[Guideline]) -> set[tuple[str, str]]:
        wanted = set(artifact_ids)
        out: set[tuple[str, str]] = set()
        for g in guidelines:
            gid = self.artifact_id(g)
            if gid and gid in wanted:
                out.add((_norm(g.content.condition), _norm(g.content.action)))
        return out
