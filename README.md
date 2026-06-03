# Caker

Caker 是跑在本机的 **Agent Skills 助手**：在浏览器里对话，Agent 在**当前会话工作区**读写文件、按技能执行任务，并可选进入 **Docker 执行环境**跑项目命令。引擎（LangGraph + MCP）始终在宿主机；每个 `user` + `session` 有独立磁盘目录，数据默认落在 `./var/`。

## 功能

| 类别 | 能力 |
|------|------|
| **对话** | 多轮续聊、流式输出、附件上传、会话标题自动生成 |
| **工作区** | `read` / `write` / `glob` / `edit`；产出写入 `outputs/` |
| **技能** | `skills/` 按需加载（`call_skill` + `run_py_script`） |
| **执行环境** | 沙箱 IDE：文件树、编辑器、Web 终端、`sandbox_exec`（需确认） |
| **长时任务** | `daemon_start` 等在容器内后台跑训练/批处理 |
| **观测** | 会话 `logs/` JSONL + Web 日志面板（工具调用、token、沙箱输出） |
| **记忆** | 可选 Chroma 跨会话召回；用户偏好自动积累（`user_profile`） |
| **自省** | 只读 GitHub 镜像查看 Caker 自身源码（`caker_mirror_*`） |

## 特点

- **用户与会话分层** — 侧栏切换用户；每用户多个会话，各有工作区与聊天 thread
- **会话即沙箱** — 上传路径与 Agent 工具路径一致
- **图 + 工具 + 技能** — LangGraph 编排；MCP 原子工具；业务说明在 `skills/`
- **薄 Web、厚服务端** — 浏览器聊天与上传；Agent 与存储在本机进程
- **OpenAI 兼容 LLM** — 设置页或 `.env` 配置 Base URL / API Key / 模型（PAI-EAS、百炼、DeepSeek 等 **OpenAI 面**）
- **本地开箱** — `uvicorn` + `.env` 即可；不绑特定云厂商

## 环境要求

- **Python 3.11+**
- **LLM**：OpenAI 兼容 HTTP API（`/v1/chat/completions`、`/v1/models`）
- **沙箱 / 终端（可选）**：本机已安装 Docker；WSL2 用户请在 Linux 内跑 `uvicorn`

## 快速开始

```bash
git clone https://github.com/ecakeman/caker.git
cd caker
cp .env.example .env
# 编辑 .env：至少填写 LLM_MODEL_NAME、LLM_BASE_URL、LLM_API_KEY

pip install -e ".[dev]"   # 或：uv sync && uv pip install -e .
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

浏览器打开 **http://127.0.0.1:8000/**

- 顶栏 **设置**：按用户配置 LLM（会写入 `var/web/settings.json`）
- 侧栏 **新对话** → 上传文件 → 提问
- 需要跑项目代码时 → **进入执行环境**（见 [用户指南](docs/user-guide.md)）

**详细使用说明** → [docs/user-guide.md](docs/user-guide.md)

## 数据目录（默认）

| 路径 | 内容 |
|------|------|
| `var/workspace/<user>/<session>/` | 会话工作区（`data/`、`outputs/`、`compose/`、`logs/`） |
| `var/web/settings.json` | Web 设置、每用户 LLM 配置（`llmByUser`） |
| `var/web/sessions/` | 会话列表元数据（标题、更新时间） |
| `var/state.db` | LangGraph 多轮对话检查点 |
| `var/chroma/` | 向量记忆（需 `EMBEDDING_*`） |

`WORKSPACE_ROOT` 可在 `.env` 中覆盖。

## 文档

| 文档 | 说明 |
|------|------|
| **[user-guide.md](docs/user-guide.md)** | **详细使用说明**（界面、设置、沙箱、日志、FAQ） |
| [execution-runtime-v2.md](docs/execution-runtime-v2.md) | 执行环境 / Docker / API |
| [observability.md](docs/observability.md) | 观测日志格式与配置 |
| [engine_log_format_v1.md](docs/engine_log_format_v1.md) | `engine.jsonl` 规范 |
| [agent_skills_build_guide.md](docs/agent_skills_build_guide.md) | 从零搭建引擎 |
| [milestones.md](docs/milestones.md) | 里程碑验收 |
| [docs/README.md](docs/README.md) | 文档索引 |

开发：`pytest` · `scripts/validate_tools_skills.py` · 协作见 [AGENTS.md](AGENTS.md)

## 仓库

https://github.com/ecakeman/caker
