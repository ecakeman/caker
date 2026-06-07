# Parlant ABM 智能经纪人

独立项目位于 `dev/apps/parlant`，与 `dev/apps/broker` **代码完全解耦**。
仅复制原始数据：`data/raw/guidelines.json`、`data/raw/journeys.json`。

## 模块边界

| 模块 | 职责 | 输入 | 输出 |
|------|------|------|------|
| `data_pipeline/` | 数据处理 | `data/raw/*.json` | `artifacts/` |
| `app/` | Parlant 运行时 + 两阶段 matching | `artifacts/manifest.json` | Gateway / eval 报告 |

**唯一契约**：`artifacts/manifest.json` 及其指向的文件。两个模块互不 import。

## 模型配置

所有需要模型的位置统一使用 `.env` 中两套模型：

- Chat LLM: `qwen3.5-397b-fp8` (PAI-EAS)
- Embedding: `text-embedding-v4` (DashScope, 1024 维)

## 静态数据（来自 broker，仅复制文件）

- `data/profile/agent.md` — 卷叔人格设定（注入 agent `description`）
- `data/glossary/terms.json` — 领域术语表（bootstrap 时 `create_term`）
- `data/sim_scenarios/scenarios.json` — 20 轮客户模拟场景库

## 快速开始

```bash
cd dev/apps/parlant
cp .env.example .env   # 或沿用已有 .env
python -m venv .venv && .venv/bin/pip install -e ".[test]"

# 1) 数据处理（生成 artifacts）
bash scripts/run_pipeline.sh

# 2) 回归评估（matching 召回）
.venv/bin/python evals/run_eval.py

# 3) 启动 Parlant Gateway（含 profile + glossary + guidelines + journeys）
bash scripts/run_gateway.sh

# 4) 20 轮多情景客户模拟（需 gateway 已启动；基于 pipeline v2 artifacts 自动生成情景）
bash scripts/customer_sim_20.sh --turns 20
```

### 客户模拟观测（方案 A：两层产物）

默认仅输出两份文件（`TELEMETRY_LEVEL` 未设或为 `default`）：

| 产物 | 路径 |
|------|------|
| 内容记录（每轮一条，可回放） | `var/customer_sim/<run_id>/records/content_record.jsonl` |
| 汇总报告（20 轮跑完生成） | `var/customer_sim/<run_id>/reports/summary.md` |

Gateway 运行时写入全局缓冲 `var/content_record.jsonl`；sim 按 `session_id` 切片到上述 run 目录。

**Debug 开关**（可选，默认关闭）：

```bash
export TELEMETRY_LEVEL=debug
bash scripts/customer_sim_20.sh --turns 20
# 额外输出：var/customer_sim/<run_id>/debug/turn_pipeline_full.jsonl
```

旧版 `telemetry/turn_pipeline.jsonl`、`simulation/`、`dialogue/` 等臃肿目录已弃用，见 `deprecated/` 与 `CHANGELOG_migration.md`。

## 数据处理产物

- `artifacts/reports/audit_report.json` — 原始数据审计（schema、工具分布、相似/重复、journey 图问题）
- `artifacts/normalized/` — 带稳定 ID 的 guidelines / journeys
- `artifacts/schema_contract.json` — normalized schema 契约
- `artifacts/scope_map.json` — global / journey / state / always-on 候选池
- `artifacts/relationships.json` — exclusion / dependency / entailment / disambiguation
- `artifacts/reports/journeys/` — journey 治理报告 + mermaid 图
- `artifacts/indexes/` — BM25 + 向量索引
- `artifacts/manifest.json` — 运行时唯一入口（`pipeline_version: 2`）
- `artifacts/variables.json` / `canned_responses.json` / `glossary.json` — ABM 扩展资产
- `artifacts/retrievers_corpus/` — 检索语料与 RRF/rerank 配置
- `artifacts/reports/audit_extended.json` — 索引一致性 / scope / 关系图审计

## 两阶段 Guideline Matching（`app/matching/`）

1. Query 构建（可选 LLM 改写，`MATCHING_QUERY_REWRITE=1`）
2. BM25 + 向量双路召回，RRF 融合
3. Scope filter + adaptive K（高风险/低置信扩大候选）
4. Rerank（向量相似度 + RRF 加权）
5. Always-on 注入 + relationship 闭包
6. 小候选 LLM 精判（`judge.py`）
7. 离线 eval trace：`var/eval_matching_traces.jsonl`；Gateway runtime 观测：`var/content_record.jsonl`（`TELEMETRY_LEVEL=debug` 时另写 `var/turn_pipeline.jsonl`）

## 评估

```bash
.venv/bin/python evals/run_eval.py
# -> artifacts/reports/eval_report.json
```

当前 golden 集（10 条）：topK 召回率 80%，高风险 always-on 召回率 100%。
