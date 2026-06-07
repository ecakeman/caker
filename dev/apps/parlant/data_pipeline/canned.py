from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STRICT_KEYWORDS = ("合规", "返佣", "监管", "违法", "诈骗", "误导", "隐私", "拒答")


def build_canned_responses(guidelines: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for g in guidelines:
        text = f"{g['condition_text']} {g['action_text']}"
        risk = g.get("risk_level") == "high" or any(k in text for k in STRICT_KEYWORDS)
        if not risk:
            continue
        items.append(
            {
                "id": f"canned_{g['guideline_id']}",
                "guideline_id": g["guideline_id"],
                "trigger_hint": g["condition_text"][:200],
                "response_template": g["action_text"][:500],
                "review_required": True,
                "strict_recommended": any(k in text for k in STRICT_KEYWORDS),
                "usage": "candidate_only_not_auto_send",
                "confidence": 0.6,
                "inference": "derived_from_high_risk_guideline",
            }
        )
    return {
        "version": "1",
        "policy": {
            "production_mode": "review_required",
            "strict_scenarios": "require_human_review_before_enable",
            "default_enable": False,
        },
        "items": items,
        "stats": {"count": len(items), "strict_count": sum(1 for i in items if i["strict_recommended"])},
    }


def write_canned(guidelines_path: Path, out_path: Path) -> dict[str, Any]:
    guidelines = json.loads(guidelines_path.read_text(encoding="utf-8"))
    doc = build_canned_responses(guidelines)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"canned_path": str(out_path), **doc["stats"]}
