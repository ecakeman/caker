#!/usr/bin/env python3
"""Build reports/summary.md from records/content_record.jsonl."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any
import re

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.governance.metrics import (  # noqa: E402
    compute_governance_metrics,
    load_baseline,
    render_governance_section,
)
from data_pipeline.fingerprint import build_manifest_fingerprint  # noqa: E402

IMAGE_CLAIM_RE = re.compile(
    r"(已发送图片|已发图|我发你图|发你图了|如下图|图片发你|图发你|"
    r"刚给你发|刚发你的图|这就发给你|发了张图|发了几张图|刚才发你的)"
)
MATERIAL_TOKEN_RE = re.compile(r"\[(?:图片|链接|引用):[A-Za-z0-9_\-:.]+\]|\[暂无可用图片\]")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = min(len(values) - 1, max(0, round((p / 100) * (len(values) - 1))))
    return float(values[idx])


def dist(values: list[float]) -> dict[str, float]:
    return {
        "p50": round(percentile(values, 50), 2),
        "p95": round(percentile(values, 95), 2),
        "avg": round(sum(values) / len(values), 2) if values else 0.0,
    }


def render_summary(rows: list[dict[str, Any]], *, run_dir: Path) -> str:
    n = len(rows)
    e2e = [float(r["e2e_ms"]) for r in rows if r.get("e2e_ms") is not None]
    slowest = Counter(str(r.get("slowest_stage") or "") for r in rows if r.get("slowest_stage"))
    no_match = Counter(str(r.get("no_match_reason") or "unknown") for r in rows)
    matched_nonempty = sum(1 for r in rows if int(r.get("matched_count") or 0) > 0)
    recall_vals = [float(r["recall_at_k"]) for r in rows if r.get("recall_at_k") is not None]
    progress = sum(1 for r in rows if r.get("progress_pass"))
    compliance = sum(1 for r in rows if r.get("compliance_pass"))
    grounded = sum(1 for r in rows if r.get("grounded_pass"))
    fail_reasons = Counter()
    for r in rows:
        for reason in r.get("failure_reasons") or []:
            fail_reasons[str(reason)] += 1
    llm_calls = [float(r.get("llm_calls") or 0) for r in rows]
    tokens = [float(r.get("total_tokens") or 0) for r in rows]
    k_vals = [float(r["K"]) for r in rows if r.get("K") is not None]
    always_on = [float(r.get("always_on_count") or 0) for r in rows]
    closure = [float(r.get("closure_added_count") or 0) for r in rows]
    tool_total = sum(len(r.get("tools_called") or []) for r in rows)
    tool_names = Counter()
    tool_fail = 0
    topic_miss_count = 0
    missing_params_count = 0
    fallback_no_image_count = 0
    fabricated_image_claim_count = 0
    rendered_material_tokens = Counter()
    enforcement_calls = [float(r.get("enforcement_calls_count") or 0) for r in rows]
    enforcement_tokens = [float(r.get("enforcement_tokens_total") or 0) for r in rows]
    for r in rows:
        reply = str(r.get("agent_reply") or "")
        for token in r.get("rendered_material_tokens") or MATERIAL_TOKEN_RE.findall(reply):
            rendered_material_tokens[str(token)] += 1
        if "[暂无可用图片]" in reply:
            fallback_no_image_count += reply.count("[暂无可用图片]")
        successful_image_with_attachment = any(
            t.get("name") == "send_image"
            and t.get("ok", True)
            and (t.get("output_url") or t.get("attachment_id") or t.get("tool_call_id"))
            for t in (r.get("tools_called") or [])
        )
        if IMAGE_CLAIM_RE.search(reply):
            fabricated_image_claim_count += 1
        for t in r.get("tools_called") or []:
            tool_names[str(t.get("name") or "unknown")] += 1
            if t.get("error_type") == "topic_miss":
                topic_miss_count += 1
            if t.get("error_type") == "missing_params":
                missing_params_count += 1
            if t.get("fallback_no_image"):
                fallback_no_image_count += 1
            if not t.get("ok", True):
                tool_fail += 1

    slow_turns = sorted(
        [{"turn": r.get("turn"), "e2e_ms": r.get("e2e_ms"), "slowest_stage": r.get("slowest_stage")} for r in rows],
        key=lambda x: float(x.get("e2e_ms") or 0),
        reverse=True,
    )[:5]

    samples = rows[: min(5, n)]
    manifest_fp = build_manifest_fingerprint(ROOT / "artifacts" / "manifest.json")
    lines = [
        "# customer_sim 汇总报告",
        "",
        "## Gate / Manifest",
        "",
        f"- manifest_sha256: `{manifest_fp['manifest_sha256']}`",
        f"- missing_required_artifacts: `{', '.join(manifest_fp['missing_required_artifacts']) if manifest_fp['missing_required_artifacts'] else 'none'}`",
        "- command_outputs: see batch-level `reports/summary.md` when run via `scripts/run_all_15_scenarios.sh`",
        "",
        f"目录: `{run_dir}`",
        f"轮次: {n}",
        "",
        "## 速度",
        "",
        f"- E2E p50: **{dist(e2e)['p50']} ms** | p95: **{dist(e2e)['p95']} ms** | avg: {dist(e2e)['avg']} ms",
        "",
        "### 慢段归因（slowest_stage 计数）",
        "",
    ]
    for stage, cnt in slowest.most_common():
        if stage:
            lines.append(f"- {stage}: {cnt}")
    if not slowest:
        lines.append("- （无）")
    lines.extend(["", "### Top 慢轮次", ""])
    for t in slow_turns:
        lines.append(f"- turn {t.get('turn')}: {t.get('e2e_ms')} ms ({t.get('slowest_stage')})")

    lines.extend(
        [
            "",
            "## 准确",
            "",
            f"- matched 非空轮次: **{matched_nonempty}/{n}** ({round(matched_nonempty / max(n, 1) * 100, 1)}%)",
            f"- recall@K avg（全轮，已稀释）: **{round(sum(recall_vals) / len(recall_vals), 4) if recall_vals else 0}**",
            "",
            "### no_match_reason 分布",
            "",
        ]
    )
    for reason, cnt in no_match.most_common():
        lines.append(f"- {reason}: {cnt}")

    lines.extend(
        [
            "",
            "## 质量",
            "",
            f"- progress_pass: {progress}/{n} ({round(progress / max(n, 1) * 100, 1)}%)",
            f"- compliance_pass: {compliance}/{n} ({round(compliance / max(n, 1) * 100, 1)}%)",
            f"- grounded_pass: {grounded}/{n} ({round(grounded / max(n, 1) * 100, 1)}%)",
            "",
            "### 失败原因分布",
            "",
        ]
    )
    for reason, cnt in fail_reasons.most_common():
        lines.append(f"- {reason}: {cnt}")
    if not fail_reasons:
        lines.append("- （无）")

    lines.extend(
        [
            "",
            "## 影响因素",
            "",
            f"- K 分布 p50={dist(k_vals)['p50'] if k_vals else 0} avg={dist(k_vals)['avg'] if k_vals else 0}",
            f"- always_on_count avg={dist(always_on)['avg']}",
            f"- closure_added_count avg={dist(closure)['avg']}",
            f"- LLM calls/轮 p50={dist(llm_calls)['p50']} avg={dist(llm_calls)['avg']}",
            f"- total_tokens/轮 p50={dist(tokens)['p50']} avg={dist(tokens)['avg']}",
            f"- 工具调用总数: {tool_total}（失败 {tool_fail}）",
            f"- topic_miss_count: {topic_miss_count}",
            f"- missing_params_count: {missing_params_count}",
            f"- fallback_no_image_count: {fallback_no_image_count}",
            f"- fabricated_image_claim_count: {fabricated_image_claim_count}",
            f"- rendered_material_tokens_count: {sum(rendered_material_tokens.values())}",
            f"- enforcement_calls/轮 p50={dist(enforcement_calls)['p50']} avg={dist(enforcement_calls)['avg']}",
            f"- enforcement_tokens/轮 p50={dist(enforcement_tokens)['p50']} avg={dist(enforcement_tokens)['avg']}",
            "",
            "### 工具分布",
            "",
        ]
    )
    for name, cnt in tool_names.most_common():
        lines.append(f"- {name}: {cnt}")
    if not tool_names:
        lines.append("- （无）")
    lines.extend(["", "### 可见物料 token", ""])
    for token, cnt in rendered_material_tokens.most_common():
        lines.append(f"- {token}: {cnt}")
    if not rendered_material_tokens:
        lines.append("- （无）")
    scenario_id = str(rows[0].get("scenario_id") or "") if rows else ""
    gov = compute_governance_metrics(rows, root=ROOT, scenario_id=scenario_id)
    baseline = load_baseline(ROOT)
    lines.extend(render_governance_section(gov, baseline=baseline))

    lines.extend(
        [
            "",
            "## 附录：content_record 抽样",
            "",
        ]
    )
    for s in samples:
        lines.append(f"### turn {s.get('turn')} ({s.get('scenario_id')})")
        lines.append(f"- user: {s.get('user_message', '')[:120]}…")
        lines.append(f"- agent: {s.get('agent_reply', '')[:120]}…")
        lines.append(
            f"- e2e={s.get('e2e_ms')}ms slowest={s.get('slowest_stage')} "
            f"matched={s.get('matched_count')} reason={s.get('no_match_reason')}"
        )
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    record_path = run_dir / "records" / "content_record.jsonl"
    rows = read_jsonl(record_path)
    report = render_summary(rows, run_dir=run_dir)
    out = run_dir / "reports" / "summary.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
