# 文档

本目录为 Caker 使用与开发说明；项目介绍见根目录 [README.md](../README.md)。

## 使用者

| 文档 | 内容 |
|------|------|
| **[user-guide.md](user-guide.md)** | **详细使用说明**：安装、设置、工作区、沙箱、日志、FAQ |
| [execution-runtime-v2.md](execution-runtime-v2.md) | 执行环境工作台、Docker、相关 API |
| [observability.md](observability.md) | 会话 `logs/` 观测与 `.env` 配置 |

## 开发者 / 实现者

| 文档 | 内容 |
|------|------|
| [milestones.md](milestones.md) | 已实现里程碑与验收 |
| [agent_skills_build_guide.md](agent_skills_build_guide.md) | 分阶段从零搭建引擎 |
| [engine_log_format_v1.md](engine_log_format_v1.md) | `engine.jsonl` 字段规范 |

## 仓库根目录

| 文件 | 说明 |
|------|------|
| [AGENTS.md](../AGENTS.md) | 协作约定 |
| [system_prompt.md](../system_prompt.md) | Agent 系统提示（非使用手册） |

## 写文档放哪

| 写什么 | 放哪 |
|--------|------|
| 介绍 / 功能 / 快速开始 | 根 `README.md` |
| 怎么点界面、怎么配 LLM、FAQ | `user-guide.md` |
| 改了什么、怎么验 | `milestones.md` |
| 跟写步骤与骨架 | `agent_skills_build_guide.md` |

## 数据目录（默认）

| 路径 | 作用 |
|------|------|
| `var/workspace/<user>/<session>/` | 会话沙箱；`data/uploads/` 为上传 |
| `var/web/settings.json` | Web 设置、每用户 LLM（`llmByUser`） |
| `var/web/sessions/` | 会话列表 JSON |
| `var/state.db` | 多轮对话检查点 |
| `var/chroma/` | 跨会话语义记忆（可选） |

`WORKSPACE_ROOT` 默认 `./var/workspace`（`.env` 可改）。
