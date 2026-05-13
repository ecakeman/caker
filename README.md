# caker

在本地复现 [Agent Skills 跟写指南](docs/agent_skills_build_guide.md) 中的里程碑实现；架构说明见 [深度研究报告](docs/user_attachments_session_a29c06ca28284858b68f5de84ede3306_outputs_agent_skills_deep_research_report.md)。

## 里程碑与正式代码路径（M0–M5）

以下路径为**当前仓库已实现**内容，与指南中个别命名（如 `result_text`）不一致处见各节说明。

### M0 项目脚手架

| 路径 | 说明 |
|------|------|
| [pyproject.toml](pyproject.toml) | 依赖与可编辑安装 |
| [app/main.py](app/main.py) | FastAPI 应用、`GET /health` |
| [app/config.py](app/config.py) | `pydantic-settings` 读 `.env`（`LLM_*`、存储等） |
| [app/__init__.py](app/__init__.py) | 包初始化 |
| [.env.example](.env.example) | 环境变量模板 |
| [docker-compose.yaml](docker-compose.yaml) | 可选本地依赖（Postgres / MinIO / Chroma） |
| [tests/test_m0_health.py](tests/test_m0_health.py) | `/health` 冒烟测试 |

**验证**：`curl -s http://127.0.0.1:8000/health` → `{"ok":true}`。

### M1 单轮 echo

| 路径 | 说明 |
|------|------|
| [app/api/chat.py](app/api/chat.py) | `APIRouter(prefix="/api/v2")`、`EchoIn` / `EchoOut`、`POST /echo` |
| [app/main.py](app/main.py) | `app.include_router(chat_router)`（与 M0 同文件） |

**验证**：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v2/echo \
  -H 'content-type: application/json' \
  -d '{"message":"hi"}'
```

### M2 接 LLM（非流式）

| 路径 | 说明 |
|------|------|
| [app/runtime/llm.py](app/runtime/llm.py) | `get_llm()`（`langchain_openai.ChatOpenAI`）、`clear_llm_cache()` |
| [app/api/chat.py](app/api/chat.py) | `ChatOnceIn` / `ChatOnceOut`、`POST /chat-once` |
| [.env.example](.env.example) | `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL_NAME`、`LLM_TEMPERATURE` |

**验证**：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-once \
  -H 'content-type: application/json' \
  -d '{"message":"用一句话介绍 LangGraph"}'
```

### M3 LangGraph 雏形

| 路径 | 说明 |
|------|------|
| [app/runtime/state.py](app/runtime/state.py) | `GraphState`：`messages`（`add_messages`）、`input`、`result`、`skip_inject_system` |
| [app/runtime/nodes.py](app/runtime/nodes.py) | `start` → `inject_system` → `inject_user` → `llm` → `end` 各节点 |
| [app/runtime/graph.py](app/runtime/graph.py) | `StateGraph` 编排、`build_graph()`、`GRAPH` |
| [app/api/chat.py](app/api/chat.py) | `ChatGraphIn` / `ChatGraphOut`、`POST /chat-graph` |

**与指南差异（刻意设计）**：首轮 `messages` 为空，用户句走 `input`，由 `inject_user_node` 写入 `HumanMessage`，避免 System 排在 Human 之后；聚合字段名为 **`result`**（非指南骨架里的 `result_text`）。

**验证**：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' \
  -d '{"message":"hi"}'
```

### M4 SSE 流式输出

| 路径 | 说明 |
|------|------|
| [app/runtime/sse.py](app/runtime/sse.py) | `sse_pack`、`sse_comment`（SSE 帧与注释行） |
| [app/runtime/graph.py](app/runtime/graph.py) | `iter_graph_stream_events`：`GRAPH.astream_events(..., version="v2")` |
| [app/runtime/llm.py](app/runtime/llm.py) | `stream_messages`；`get_llm_with_tools`（`bind_tools`） |
| [app/runtime/nodes.py](app/runtime/nodes.py) | `llm_node`：`get_llm_with_tools` + `await ...ainvoke`（M5 起绑定工具；满足 `astream_events`） |
| [app/api/chat.py](app/api/chat.py) | `POST /stream`、`StreamingResponse`；`event: delta` / `done` / `error`，`inputs` 与 `chat-graph` 一致 |

**验证**：

```bash
curl -N -X POST http://127.0.0.1:8000/api/v2/stream \
  -H 'content-type: application/json' \
  -d '{"message":"数到5"}'
```

预期：多条 `event: delta`（`data` 为 JSON，含 `text`），最后 `event: done`。流式请求须打到 **本机 caker**（如 `127.0.0.1:8000`），不要对上游 LLM 的 `openapi.*` 域名拼 `/api/v2/stream`。

**运维提示**：经 nginx 等反代时，需关闭对 SSE 的缓冲（如 `proxy_buffering off`），否则客户端看不到逐块输出。

### M5 第一个 Tool：`Read`（尚未接 ToolNode）

| 路径 | 说明 |
|------|------|
| [app/tools/__init__.py](app/tools/__init__.py) | 包初始化（空文件即可） |
| [app/tools/base.py](app/tools/base.py) | `build_default_tools()`，当前返回 `[ReadTool()]` |
| [app/tools/read_tool.py](app/tools/read_tool.py) | `Read`：`BaseTool` + 路径校验（`WORKSPACE_ROOT/demo/…`，M5 固定 `session_id=demo`） |
| [app/runtime/llm.py](app/runtime/llm.py) | `get_llm_with_tools(tools)` → `bind_tools` |
| [app/runtime/nodes.py](app/runtime/nodes.py) | `llm_node` 使用 `get_llm_with_tools(_TOOLS)` |

**与指南一致的行为**：图内**仍无 `ToolNode`**；模型若决定读文件，响应里常见 **`tool_calls` 含 `Read`**，**`reply`/正文可能为空**——属 M5 预期，**M6** 再接工具执行与回灌闭环。

**验证（需已配置 `LLM_*`，并准备演示文件）**：

```bash
mkdir -p /tmp/skills/demo/data && echo "hello world" > /tmp/skills/demo/data/a.txt
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' \
  -d '{"message":"请用 Read 工具读 data/a.txt 的前 5 行"}'
```

若上游模型配合，可在返回 JSON / 日志侧观察到对 `Read` 的调用意图（本阶段不保证自然语言摘要，因工具尚未执行）。

---

## README 维护约定

每完成一个里程碑（M5 及以后），在本节 **「里程碑与正式代码路径」** 中追加对应小节：列出**新增或实质性修改**的文件路径、验证命令；若与 `docs/agent_skills_build_guide.md` 有故意偏差，用一两句写清原因。

---

## 快速开始

```bash
cd caker
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

可选：启动 Postgres / MinIO / Chroma（Chroma 映射到本机 **8001**）：

```bash
docker compose up -d
```

## 文档依据

- 里程碑与分工：`docs/agent_skills_build_guide.md`
- 协作与提交流程：根目录 [AGENTS.md](AGENTS.md)
- 四层架构与图节点：`docs/user_attachments_session_a29c06ca28284858b68f5de84ede3306_outputs_agent_skills_deep_research_report.md`
