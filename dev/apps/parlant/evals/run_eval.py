from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.artifacts import load_artifacts
from app.config import load_settings
from app.matching.engine import GuidelineMatchingEngine


def _recall_hit(trace_texts: list[str], expected_parts: list[str]) -> bool:
    blob = " ".join(trace_texts)
    return all(part in blob for part in expected_parts)


def _always_on_recall(trace_ids: list[str], always_on: list[str]) -> bool:
    if not always_on:
        return True
    present = set(trace_ids)
    return all(gid in present for gid in always_on)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    settings = load_settings(root)
    bundle = load_artifacts(settings.artifacts_root)
    engine = GuidelineMatchingEngine(bundle, settings)
    trace_path = root / "var" / "eval_matching_traces.jsonl"
    cases_path = root / "evals" / "golden_cases.jsonl"
    results = []
    always_on = bundle.scope_map.get("always_on") or []
    for line in cases_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        trace = engine.match(
            case["query"],
            active_journey_id=case.get("active_journey_id"),
            active_state_id=case.get("active_state_id"),
            use_llm_judge=False,
            write_trace=True,
            trace_path=trace_path,
        )
        retrieval_texts = [r.get("condition_text", "") for r in trace.reranked or trace.retrieval]
        final_texts = [m.get("condition_text", "") for m in trace.final_matches]
        retrieved_ids = [r["guideline_id"] for r in trace.retrieval]
        hit_topk = _recall_hit(retrieval_texts, case["expected_guideline_contains"])
        hit_final = _recall_hit(final_texts, case["expected_guideline_contains"])
        high_risk_case = case.get("tier") == "high_risk"
        always_on_ok = _always_on_recall(retrieved_ids, always_on) if high_risk_case else True
        results.append({
            "id": case["id"],
            "tier": case.get("tier"),
            "recall_topk": hit_topk,
            "recall_final": hit_final,
            "always_on_recall": always_on_ok,
            "adaptive_k": trace.adaptive_k,
            "retrieved_count": len(trace.retrieval),
            "relationship_actions": len(trace.relationship_trace),
            "retrieved": retrieved_ids[:10],
            "always_on_injected": trace.always_on_injected,
        })
    high_risk_cases = [r for r in results if r.get("tier") == "high_risk"]
    report = {
        "case_count": len(results),
        "recall_topk_rate": sum(1 for r in results if r["recall_topk"]) / max(len(results), 1),
        "recall_final_rate": sum(1 for r in results if r["recall_final"]) / max(len(results), 1),
        "high_risk_always_on_recall_rate": (
            sum(1 for r in high_risk_cases if r["always_on_recall"]) / max(len(high_risk_cases), 1)
        ),
        "trace_log": str(trace_path.relative_to(root)),
        "cases": results,
    }
    out = settings.artifacts_root / "reports" / "eval_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
