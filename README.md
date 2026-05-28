# Caker

**本地 Agent Skills 运行时** · 基于 LangGraph

在浏览器里对话、上传文件、管理会话工作区；Agent 在**会话沙箱**内读写文件、调用技能与 MCP 工具。适合本机开发与跟写 [Agent Skills 指南](docs/agent_skills_build_guide.md) 对照实现。

[设计理念](docs/design.md) · [用户指南](docs/user-guide.md) · [文档索引](docs/README.md) · [实现进度 M0–M13](docs/milestones.md)

---

## 能做什么

| 能力 | 说明 |
|------|------|
| **对话** | 流式 / 非流式；多轮上下文保存在 `var/state.db` |
| **工作区** | 每用户、每会话独立目录；`+` 上传到 `data/uploads/` |
| **工具** | read / write / glob / edit、call_skill、脚本执行、Chroma 记忆等（MCP 统一注册） |
| **技能** | `skills/` 下 Agent Skills 规范目录，按需加载说明 |
| **Web** | 侧栏会话列表、工作区面板、复制路径、本机打开资源管理器（Win/WSL/Mac） |
| **压缩** | 长对话软压缩上下文，减少超长报错 |

Agent **不能**访问你电脑上的任意路径，只能操作当前会话工作区。

---

## 快速开始

```bash
git clone https://github.com/ecakeman/caker.git
cd caker
cp .env.example .env
# 编辑 .env：LLM_*、WORKSPACE_ROOT=./var/workspace；MemPalace 需 EMBEDDING_*
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

浏览器打开 **http://127.0.0.1:8000/**

```bash
curl -s http://127.0.0.1:8000/health   # {"ok":true}
```

可选：`docker compose up -d chroma`（向量记忆；默认也可用 `./var/chroma`）。

更细的界面说明见 **[用户指南](docs/user-guide.md)**。

---

## 数据存在哪

| 路径 | 内容 |
|------|------|
| `var/workspace/<user>/<session>/` | 会话沙箱（上传、产出、skills 链接） |
| `var/web/` | Web 用户、会话列表、设置 |
| `var/state.db` | LangGraph 多轮检查点 |
| `var/chroma/` | MemPalace 向量（可选） |

---

## 项目结构（简图）

```text
app/api/          HTTP、SSE、Web API
app/runtime/      LangGraph 图与节点
app/mcp/          工具注册与适配
app/workspace/    会话目录沙箱
skills/           Agent Skills 包
web/              聊天界面（静态）
docs/             用户指南、设计理念、里程碑进度
```

---

## 文档

| 文档 | 适合谁 |
|------|--------|
| [docs/user-guide.md](docs/user-guide.md) | 使用 Web、工作区、上传、FAQ |
| [docs/design.md](docs/design.md) | 设计理念与边界 |
| [docs/milestones.md](docs/milestones.md) | 各里程碑文件路径与 curl 验收 |
| [docs/agent_skills_build_guide.md](docs/agent_skills_build_guide.md) | 从零跟写实现 |
| [docs/caker-base-knowledge.md](docs/caker-base-knowledge.md) | LangGraph / 工具概念 |
| [AGENTS.md](AGENTS.md) | 在本仓库协作的 AI 约定 |

---

## 开发

```bash
uv run --extra dev pytest tests/ -q
uv run python scripts/validate_tools_skills.py
```

**进度**：M0–M13 已落地，详见 [docs/milestones.md](docs/milestones.md)。协作与 checkpoint 见 [AGENTS.md](AGENTS.md)。

---

## License

见仓库根目录（若未单独声明，以项目维护者为准）。
