# Pipeline v2 + Multi-scenario Sim — Migration Changelog

## 破坏性变更摘要

- **唯一契约**：`artifacts/manifest.json` 必须为 `pipeline_version: "2"`；Gateway / sim 启动时拒绝 v1。
- **旧 artifacts**：首次跑 v2 pipeline 时自动归档到 `deprecated/artifacts_v1_<timestamp>/`。
- **旧 sim**：`scripts/customer_sim_20.py` → `deprecated/scripts/`；`data/sim_scenarios/` → `deprecated/data/sim_scenarios_v1/`。
- **默认 sim 入口**：`bash scripts/customer_sim_20.sh` 现调用 `scripts/customer_sim_multiscenario.py`（多情景 v2）。

## 旧 → 新文件映射

| 旧路径 | 新路径 / 状态 |
|--------|----------------|
| `artifacts/manifest.json` (version 1) | `artifacts/manifest.json` (pipeline_version 2, 含 `artifacts.*.sha256`) |
| `artifacts/scope_map.json` | 同路径；新增 `fallback_rules.unknown_state_scope` |
| `artifacts/relationships.json` | 同路径；合并 `data/raw/relations.json` priority + entailment/dependency |
| — | `artifacts/variables.json` |
| — | `artifacts/canned_responses.json` |
| — | `artifacts/glossary.json` |
| — | `artifacts/retrievers_corpus/corpus.jsonl` |
| — | `artifacts/retrievers_corpus/retrieval_config.json` |
| — | `artifacts/reports/audit_extended.json` |
| `artifacts/indexes/*` | 重建；`index_meta.json` 标注 alignment |
| `scripts/customer_sim_20.py` | `deprecated/scripts/customer_sim_20.py` |
| `data/sim_scenarios/scenarios.json` | `deprecated/data/sim_scenarios_v1/scenarios.json` |
| 手写单场景 `--scenario` | `simulation/scenario_plan.json`（由 artifacts 自动生成） |

## 新 Pipeline 产物清单

```
artifacts/
  manifest.json              # 唯一入口 + per-artifact sha256
  normalized/{guidelines,journeys}.json
  scope_map.json
  relationships.json
  variables.json
  canned_responses.json
  glossary.json
  retrievers_corpus/{corpus.jsonl,retrieval_config.json}
  indexes/{bm25_corpus.json,condition_vectors.npy,index_meta.json,records.jsonl}
  reports/{audit_report.json,audit_extended.json,journeys/...}
```

## 默认命令（新体系）

```bash
bash scripts/run_pipeline.sh          # 数据资产化 v2
bash scripts/restart_gateway.sh       # Gateway（bootstrap 读 manifest v2）
bash scripts/customer_sim_20.sh       # 20 轮多情景 sim v2
```

## Telemetry（方案 A 瘦身）

**默认（两层）**

| 旧 | 新 |
|----|-----|
| `var/customer_sim/<run_id>/telemetry/turn_pipeline.jsonl` | `var/customer_sim/<run_id>/records/content_record.jsonl` |
| `summary_report.md` / `scripts/summarize_customer_sim_run.py` | `reports/summary.md` / `scripts/build_sim_summary.py` |
| `simulation/`、`dialogue/`、`inspect/`、`run_meta.json` | 默认不再生成 |

- Gateway：`var/content_record.jsonl`（紧凑字段：e2e、matcher、journey、tools、LLM 汇总、judge）
- Debug：`TELEMETRY_LEVEL=debug` → `var/turn_pipeline.jsonl` + run 内 `debug/turn_pipeline_full.jsonl`
- 已移至 `deprecated/scripts/`：`summarize_customer_sim_run.py`、`analyze_customer_sim_compare.py`

## 回滚

如需回滚 v1 artifacts：从 `deprecated/artifacts_v1_*` 拷回 `artifacts/` 并改 `pipeline_version`（不推荐；Gateway 将拒绝非 v2 manifest）。
