# 治理阶段（Governance）

硬约束：每项改动必须有**可落实**改动点 + **可评判** before/after 指标（写入 `reports/summary.md` §治理指标）。

## 默认回归链

```bash
bash scripts/run_pipeline.sh
bash scripts/restart_gateway.sh
bash scripts/customer_sim_all_scenarios.sh   # 15 情景串行
```

对比 baseline：`artifacts/governance_baseline.json`（batch_20260607_040153）

## A. 数据治理

| ID | 状态 | 改动点 | 验收指标 |
|----|------|--------|----------|
| A1 | 已启动 | `data_pipeline/tool_guidelines.py` → `guidelines.json` 增 `is_tool_trigger` 等 | tool_guideline_matched_rate ≥80%, tool_fail ≤10% |
| A2 | 已启动 | `data_pipeline/variables.py` profile_*/state_* 分层 | state_vars_coverage ≥80% |
| A3 | 已启动 | `GOVERNANCE_GLOSSARY_BOOTSTRAP_MAX=0` 停用全量 term 注入 | glossary_injected p50 ≤15, tokens -40% |
| A4 | 已启动 | `relationship_cycles.json` 环检测 | relationship_cycle_count = 0 |
| A5 | 已启动 | `data/sim_scenarios/expectations.json` | labeled_turn_ratio + recall@K_on_labeled |

## B. 项目治理

| ID | 状态 | 改动点 | 验收指标 |
|----|------|--------|----------|
| B1 | 已启动 | 移除 active_journey 强制 K=12；仅高风险升 K | E2E p50≤12s, LLM calls p50≤10, tokens -50% |
| B2 | 待办 | ARQ 分级短路 | arq_enforcement_ms_p50 -50% |
| B3 | 待办 | tool 缺参追问 | tool_fail ≤10% |
| B4 | 已启动 | `matcher_context.py` 证据投影 | matcher_rejected_all -50% |

## summary.md 固定章节

1. 速度 SLO
2. 准确 / no_match 分布
3. 质量
4. **治理指标（Governance）** ← 新增
5. 影响因素
6. 附录抽样
