from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _dist(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = min(len(values) - 1, max(0, round((p / 100) * (len(values) - 1))))
    return float(values[idx])


def load_expectations(root: Path) -> dict[str, Any]:
    for rel in (
        "data/sim_scenarios/expectations.json",
        "artifacts/scenario_expectations.json",
    ):
        p = root / rel
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    return {"scenarios": {}}


def load_baseline(root: Path) -> dict[str, Any]:
    p = root / "artifacts" / "governance_baseline.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def compute_governance_metrics(
    rows: list[dict[str, Any]],
    *,
    root: Path,
    scenario_id: str | None = None,
) -> dict[str, Any]:
    expectations_doc = load_expectations(root)
    scenario_exp = expectations_doc.get("scenarios") or {}
    sid = scenario_id or (str(rows[0].get("scenario_id")) if rows else "")
    exp = scenario_exp.get(sid) or {}
    is_tool_scenario = bool(exp.get("tool_scenario"))
    expected_gids = set(exp.get("expected_guideline_ids") or [])
    expected_tools = set(exp.get("expected_tool_calls") or [])

    tool_turns = 0
    tool_matched_turns = 0
    tool_calls = 0
    tool_fails = 0
    rejected_all = 0
    rejected_all_tool = 0
    labeled_turns = 0
    labeled_hits = 0
    arq_ms: list[float] = []
    glossary_counts: list[float] = []

    for r in rows:
        tools_called = r.get("tools_called") or []
        tool_calls += len(tools_called)
        tool_fails += sum(1 for t in tools_called if not t.get("ok", True))
        if r.get("no_match_reason") == "matcher_rejected_all":
            rejected_all += 1
        matched_ids = set(r.get("matched_guideline_ids_topN") or [])
        if int(r.get("matched_count") or 0) > 0:
            matched_ids  # keep for clarity
        user_msg = str(r.get("user_message") or "")
        wants_tool = is_tool_scenario or any(
            k in user_msg for k in ("图", "链接", "对比表", "截图", "发我")
        )
        if wants_tool:
            tool_turns += 1
            if int(r.get("matched_count") or 0) > 0 or tools_called:
                tool_matched_turns += 1
            if r.get("no_match_reason") == "matcher_rejected_all":
                rejected_all_tool += 1
        if expected_gids:
            labeled_turns += 1
            if matched_ids & expected_gids:
                labeled_hits += 1
        for st in r.get("stage_ms_top3") or []:
            if st.get("stage") == "arq_enforcement":
                arq_ms.append(float(st.get("ms") or 0))
                break
        if r.get("glossary_injected_count") is not None:
            glossary_counts.append(float(r["glossary_injected_count"]))

    n = len(rows) or 1
    return {
        "scenario_id": sid,
        "tool_scenario": is_tool_scenario,
        "tool_guideline_matched_rate": round(tool_matched_turns / max(tool_turns, 1), 4),
        "tool_fail_rate": round(tool_fails / max(tool_calls, 1), 4) if tool_calls else 0.0,
        "matcher_rejected_all_rate": round(rejected_all / n, 4),
        "matcher_rejected_all_on_tool_scenarios": round(rejected_all_tool / max(tool_turns, 1), 4),
        "labeled_turn_ratio": round(labeled_turns / n, 4),
        "recall_at_k_on_labeled_turns": round(labeled_hits / max(labeled_turns, 1), 4),
        "arq_enforcement_ms_p50": round(_dist(arq_ms, 50), 2),
        "glossary_injected_count_p50": round(_dist(glossary_counts, 50), 2) if glossary_counts else None,
        "expected_tool_calls": sorted(expected_tools),
        "thresholds": {
            "tool_guideline_matched_rate": 0.80,
            "tool_fail_rate": 0.10,
            "matcher_rejected_all_on_tool_scenarios": 0.10,
            "e2e_p50_ms": 12000,
            "e2e_p95_ms": 25000,
            "llm_calls_p50": 10,
            "token_reduction_pct": 0.50,
        },
    }


def render_governance_section(metrics: dict[str, Any], *, baseline: dict[str, Any] | None = None) -> list[str]:
    th = metrics.get("thresholds") or {}
    lines = [
        "## 治理指标（Governance）",
        "",
        "### 工具 / Matcher",
        "",
        f"- tool_guideline_matched_rate: **{metrics.get('tool_guideline_matched_rate')}** (阈值 ≥ {th.get('tool_guideline_matched_rate')})",
        f"- tool_fail_rate: **{metrics.get('tool_fail_rate')}** (阈值 ≤ {th.get('tool_fail_rate')})",
        f"- matcher_rejected_all_rate: **{metrics.get('matcher_rejected_all_rate')}**",
        f"- matcher_rejected_all_on_tool_scenarios: **{metrics.get('matcher_rejected_all_on_tool_scenarios')}** (阈值 ≤ {th.get('matcher_rejected_all_on_tool_scenarios')})",
        "",
        "### 标注评估（A5）",
        "",
        f"- labeled_turn_ratio: **{metrics.get('labeled_turn_ratio')}**",
        f"- recall@K_on_labeled_turns: **{metrics.get('recall_at_k_on_labeled_turns')}**",
        "",
        "### 性能 / 注入",
        "",
        f"- arq_enforcement_ms_p50: **{metrics.get('arq_enforcement_ms_p50')} ms**",
    ]
    if metrics.get("glossary_injected_count_p50") is not None:
        lines.append(f"- glossary_injected_count_p50: **{metrics['glossary_injected_count_p50']}** (目标 ≤ 15)")
    if baseline:
        lines.extend(["", "### Before/After（对比 baseline）", ""])
        for key in ("e2e_p50_ms", "llm_calls_p50", "total_tokens_p50", "tool_fail_rate"):
            b = (baseline.get("aggregate") or {}).get(key)
            if b is not None:
                lines.append(f"- baseline {key}: {b}")
    lines.extend(["", "### 验收结论", ""])
    fails: list[str] = []
    if float(metrics.get("tool_fail_rate") or 0) > float(th.get("tool_fail_rate") or 1):
        fails.append("tool_fail_rate 未达标")
    if float(metrics.get("tool_guideline_matched_rate") or 0) < float(th.get("tool_guideline_matched_rate") or 0):
        fails.append("tool_guideline_matched_rate 未达标")
    if fails:
        lines.append("- **未通过**: " + "; ".join(fails))
        lines.append("- 归因与下一步: 优先 A1 tool-trigger 可判定化 + B3 缺参追问；工具失败多来自 send_image topic miss。")
    else:
        lines.append("- 本 run 治理硬指标已通过（或本情景非 tool 主场景）。")
    lines.append("")
    return lines
