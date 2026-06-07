from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ALWAYS_ON_KEYWORDS = ("合规", "返佣", "监管", "违法", "诈骗", "误导", "拒答", "隐私")
REVIEW_THRESHOLD = 0.15


def _tokens(text: str) -> set[str]:
    text = text.lower()
    parts = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9_]{2,}", text))
    chars = [c for c in text if "\u4e00" <= c <= "\u9fff"]
    for i in range(len(chars) - 1):
        parts.add(chars[i] + chars[i + 1])
    return parts


def _overlap_score(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def build_scope_map(
    guidelines: list[dict[str, Any]],
    journeys: list[dict[str, Any]],
) -> dict[str, Any]:
    always_on: list[str] = []
    global_pool: list[str] = []
    journey_scoped: dict[str, list[str]] = {}
    state_scoped: dict[str, list[str]] = {}
    review_required: list[str] = []

    for g in guidelines:
        gid = g["guideline_id"]
        text = f"{g['condition_text']} {g['action_text']}"
        if g.get("risk_level") == "high" or any(k in text for k in ALWAYS_ON_KEYWORDS):
            always_on.append(gid)
            continue
        preset_jid = (g.get("journey_id") or "").strip()
        if g.get("scope") == "journey_scoped" and preset_jid:
            journey_scoped.setdefault(preset_jid, []).append(gid)
            continue
        best_j, best_s, best_score = None, None, 0.0
        for j in journeys:
            jtext = " ".join(j.get("activation_conditions") or []) + " " + (j.get("title") or "")
            score = _overlap_score(text, jtext)
            if score > best_score:
                best_j, best_score = j["journey_id"], score
            for st in j.get("states") or []:
                stext = " ".join(
                    x for x in (
                        st.get("chat_instruction"),
                        st.get("tool_instruction"),
                        st.get("state_id"),
                    ) if x
                )
                sscore = _overlap_score(text, jtext + " " + stext)
                if sscore > best_score:
                    best_j = j["journey_id"]
                    best_s = st["state_id"]
                    best_score = sscore
        if best_score >= REVIEW_THRESHOLD and best_j:
            journey_scoped.setdefault(best_j, []).append(gid)
            if best_s:
                state_scoped.setdefault(f"{best_j}::{best_s}", []).append(gid)
            g["scope"] = "state_scoped" if best_s else "journey_scoped"
            g["journey_id"] = best_j
            g["state_id"] = best_s
        else:
            global_pool.append(gid)
            g["scope"] = "global"
            if best_score > 0.05:
                review_required.append(gid)

    for j in journeys:
        jid = j["journey_id"]
        jtext_base = " ".join(j.get("activation_conditions") or []) + " " + (j.get("title") or "")
        for st in j.get("states") or []:
            stext = " ".join(
                x for x in (
                    st.get("chat_instruction"),
                    st.get("tool_instruction"),
                    st.get("state_id"),
                    st.get("summary_cn"),
                ) if x
            )
            if not stext.strip():
                continue
            key = f"{jid}::{st['state_id']}"
            pool = state_scoped.setdefault(key, [])
            for g in guidelines:
                gid = g["guideline_id"]
                if gid in always_on:
                    continue
                text = f"{g['condition_text']} {g['action_text']}"
                score = _overlap_score(text, jtext_base + " " + stext)
                if score >= 0.08 and gid not in pool:
                    pool.append(gid)
                    g.setdefault("scope", "state_scoped")
                    g["journey_id"] = jid
                    g["state_id"] = st["state_id"]
            journey_scoped.setdefault(jid, [])
            for gid in pool:
                if gid not in journey_scoped[jid]:
                    journey_scoped[jid].append(gid)

    state_unknown: list[str] = []
    for j in journeys:
        jid = j["journey_id"]
        for st in j.get("states") or []:
            key = f"{jid}::{st['state_id']}"
            if key not in state_scoped or not state_scoped.get(key):
                state_unknown.append(key)

    fallback_rules = {
        "unknown_state_scope": {
            "active": bool(state_unknown),
            "missing_state_keys": sorted(state_unknown)[:50],
            "fallback_chain": ["state_scoped", "journey_scoped", "global", "always_on"],
            "note": "When state_scoped has no candidates, relax to journey_scoped then global",
        }
    }

    return {
        "always_on": sorted(set(always_on)),
        "global": sorted(set(global_pool)),
        "journey_scoped": {k: sorted(v) for k, v in journey_scoped.items()},
        "state_scoped": {k: sorted(v) for k, v in state_scoped.items()},
        "review_required": sorted(set(review_required)),
        "fallback_rules": fallback_rules,
        "stats": {
            "always_on": len(always_on),
            "global": len(global_pool),
            "journey_buckets": len(journey_scoped),
            "state_buckets": len(state_scoped),
            "state_unknown": len(state_unknown),
            "review_required": len(review_required),
        },
    }


def write_scope_map(
    guidelines_path: Path,
    journeys_path: Path,
    out_path: Path,
) -> dict[str, Any]:
    guidelines = json.loads(guidelines_path.read_text(encoding="utf-8"))
    journeys = json.loads(journeys_path.read_text(encoding="utf-8"))
    scope = build_scope_map(guidelines, journeys)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(scope, ensure_ascii=False, indent=2), encoding="utf-8")
    updated_g = guidelines_path.parent / "guidelines.json"
    updated_g.write_text(json.dumps(guidelines, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"scope_map_path": str(out_path), **scope["stats"]}
