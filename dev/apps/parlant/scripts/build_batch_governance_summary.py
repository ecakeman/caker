#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.governance.metrics import load_baseline  # noqa: E402
from data_pipeline.fingerprint import build_manifest_fingerprint  # noqa: E402


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
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


def load_results(batch_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    path = batch_dir / "results.csv"
    if not path.is_file():
        return rows
    with path.open(encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row:
                continue
            rows.append(
                {
                    "scenario_id": row[0],
                    "status": row[1] if len(row) > 1 else "",
                    "started": row[2] if len(row) > 2 else "",
                    "ended": row[3] if len(row) > 3 else "",
                    "run_dir": row[4] if len(row) > 4 else "",
                }
            )
    return rows


def infer_run_dir(root: Path, scenario_id: str) -> Path | None:
    matches = sorted(root.glob(f"20*_{scenario_id}"))
    return matches[-1] if matches else None


def compare(current: dict[str, float], baseline: dict[str, Any]) -> dict[str, Any]:
    base = (baseline.get("aggregate") or {}) if baseline else {}
    out: dict[str, Any] = {}
    for key, value in current.items():
        b = base.get(key)
        if b is None:
            continue
        out[key] = {
            "baseline": b,
            "current": value,
            "delta": round(value - float(b), 4),
            "change_pct": round((value - float(b)) / max(float(b), 1e-9), 4),
        }
    return out


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: build_batch_governance_summary.py <batch_dir>")
    batch_dir = Path(sys.argv[1]).resolve()
    results = load_results(batch_dir)
    customer_root = ROOT / "var" / "customer_sim"

    all_rows: list[dict[str, Any]] = []
    run_refs: list[dict[str, str]] = []
    for r in results:
        run_dir = Path(r["run_dir"]) if r.get("run_dir") else infer_run_dir(customer_root, r["scenario_id"])
        if not run_dir:
            continue
        records = run_dir / "records" / "content_record.jsonl"
        rows = read_jsonl(records)
        all_rows.extend(rows)
        run_refs.append({**r, "run_dir": str(run_dir), "records": str(records), "turns": str(len(rows))})

    records_out = batch_dir / "records" / "content_record.jsonl"
    records_out.parent.mkdir(parents=True, exist_ok=True)
    records_out.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in all_rows),
        encoding="utf-8",
    )

    e2e = [float(r.get("e2e_ms") or 0) for r in all_rows]
    calls = [float(r.get("llm_calls") or 0) for r in all_rows]
    tokens = [float(r.get("total_tokens") or 0) for r in all_rows]
    rejected = sum(1 for r in all_rows if r.get("no_match_reason") == "matcher_rejected_all")
    matched = sum(1 for r in all_rows if int(r.get("matched_count") or 0) > 0)
    tool_calls = sum(len(r.get("tools_called") or []) for r in all_rows)
    tool_fails = sum(1 for r in all_rows for t in (r.get("tools_called") or []) if not t.get("ok", True))
    n = len(all_rows) or 1
    current = {
        "e2e_p50_ms": dist(e2e)["p50"],
        "e2e_p95_ms": dist(e2e)["p95"],
        "llm_calls_p50": dist(calls)["p50"],
        "total_tokens_p50": dist(tokens)["p50"],
        "matcher_rejected_all_rate": round(rejected / n, 4),
        "matched_nonempty_turn_ratio": round(matched / n, 4),
        "tool_fail_rate": round(tool_fails / max(tool_calls, 1), 4) if tool_calls else 0.0,
    }
    baseline = load_baseline(ROOT)
    fp = build_manifest_fingerprint(ROOT / "artifacts" / "manifest.json")
    diff = {
        "batch_dir": str(batch_dir),
        "turns": len(all_rows),
        "runs": run_refs,
        "current": current,
        "diff_vs_baseline": compare(current, baseline),
        "manifest_fingerprint": fp,
    }
    reports = batch_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "diff_vs_baseline.json").write_text(json.dumps(diff, ensure_ascii=False, indent=2), encoding="utf-8")

    pipeline_log = (batch_dir / "gate" / "run_pipeline_output.path").read_text(encoding="utf-8").strip() if (batch_dir / "gate" / "run_pipeline_output.path").is_file() else ""
    gateway_log = (batch_dir / "gate" / "restart_gateway_output.path").read_text(encoding="utf-8").strip() if (batch_dir / "gate" / "restart_gateway_output.path").is_file() else ""
    batch_log = str(batch_dir / "batch.log")
    lines = [
        "# Governance Batch Summary",
        "",
        "## Gate Command Outputs",
        "",
        f"- `bash scripts/run_pipeline.sh`: `{pipeline_log}`",
        f"- `bash scripts/restart_gateway.sh`: `{gateway_log}`",
        f"- `bash scripts/run_all_15_scenarios.sh`: `{batch_log}`",
        "",
        "## Manifest Fingerprint",
        "",
        f"- manifest_sha256: `{fp['manifest_sha256']}`",
        f"- missing_required_artifacts: `{', '.join(fp['missing_required_artifacts']) if fp['missing_required_artifacts'] else 'none'}`",
        "",
        "### Key Artifact SHA256",
        "",
    ]
    for key, entry in (fp.get("artifacts") or {}).items():
        lines.append(f"- `{key}`: `{entry['sha256']}` ({entry['path']})")
    lines.extend(
        [
            "",
            "## Hard Metrics",
            "",
            f"- e2e_ms_p50/p95: **{current['e2e_p50_ms']} / {current['e2e_p95_ms']}**",
            f"- llm_calls_per_turn_p50: **{current['llm_calls_p50']}**",
            f"- total_tokens_per_turn_p50: **{current['total_tokens_p50']}**",
            f"- matcher_rejected_all_ratio: **{current['matcher_rejected_all_rate']}**",
            f"- matched_nonempty_turn_ratio: **{current['matched_nonempty_turn_ratio']}**",
            f"- tool_fail_rate: **{current['tool_fail_rate']}**",
            "",
            "## Diff Vs Baseline",
            "",
        ]
    )
    for key, row in diff["diff_vs_baseline"].items():
        lines.append(
            f"- `{key}`: baseline={row['baseline']} current={row['current']} "
            f"delta={row['delta']} change_pct={row['change_pct']}"
        )
    lines.extend(["", "## Runs", ""])
    for ref in run_refs:
        lines.append(f"- {ref['scenario_id']}: {ref['turns']} turns, `{ref['run_dir']}`")
    (reports / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(reports / "summary.md")
    print(reports / "diff_vs_baseline.json")
    print(records_out)


if __name__ == "__main__":
    main()
