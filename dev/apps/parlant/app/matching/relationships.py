from __future__ import annotations

from typing import Any


def apply_relationship_closure(
    candidate_ids: list[str],
    relationships: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    selected = set(candidate_ids)
    trace: list[dict[str, Any]] = []
    excluded: set[str] = set()
    added: set[str] = set()

    for edge in relationships:
        etype = edge["type"]
        src = edge.get("source_id")
        tgt = edge.get("target_id")
        tgts = edge.get("target_ids") or ([tgt] if tgt else [])

        if etype == "exclusion" and src in selected:
            for t in tgts:
                if t in selected:
                    selected.discard(t)
                    excluded.add(t)
                    trace.append({"action": "exclude", "source": src, "target": t})

        if etype == "entailment" and src in selected:
            for t in tgts:
                if t not in selected:
                    selected.add(t)
                    added.add(t)
                    trace.append({"action": "entail", "source": src, "target": t})

        if etype == "dependency" and src in selected and tgt and tgt not in selected:
            selected.add(tgt)
            added.add(tgt)
            trace.append({"action": "dependency_add", "source": src, "target": tgt})

    ordered = [gid for gid in candidate_ids if gid in selected]
    for gid in sorted(added):
        if gid not in ordered:
            ordered.append(gid)
    return ordered, trace
