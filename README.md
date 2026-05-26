# caker

在本地复现 [Agent Skills 跟写指南](docs/agent_skills_build_guide.md) 中的里程碑实现；架构说明见 [深度研究报告](docs/user_attachments_session_a29c06ca28284858b68f5de84ede3306_outputs_agent_skills_deep_research_report.md)。

**进度一览**：**M0–M6** 已在仓库落地（见下「已完成」各节）。**M7 及以后** 仅保留与指南对齐的**目标摘要**，便于排期；某一 M 做完后，将对应小节改为与 M0–M6 相同的「路径表 + 验证」写法即可。

---

## 已完成里程碑（M0–M5）

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
| [app/runtime/nodes.py](app/runtime/nodes.py) | `llm_node`：`get_llm_with_tools` + `await ...ainvoke`（满足 `astream_events`） |
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

### M6 ToolNode + tool_calls 循环（已完成）

| 路径 | 说明 |
|------|------|
| [app/runtime/routes.py](app/runtime/routes.py) | 新增 `route_after_llm(state)`：检查最后一条是否为带 `tool_calls` 的 `AIMessage`，返回 `tools` 或 `end` |
| [app/runtime/graph.py](app/runtime/graph.py) | 图中新增 `tools` 节点；`llm` 后使用 `add_conditional_edges(..., {"tools": "tools", "end": "end"})`；`tools -> llm` 形成闭环 |
| [app/runtime/nodes.py](app/runtime/nodes.py) | 新增 `tools_node = ToolNode(_TOOLS)`；`_TOOLS` 与 `llm_node` 的 `get_llm_with_tools(_TOOLS)` 绑定列表保持一致 |

**当前闭环行为**：

- 模型在 `llm` 节点输出 `tool_calls`（如 `Read`）时，会走 `tools` 节点执行工具；
- 工具结果以 `ToolMessage` 回灌到 `messages`；
- 再回到 `llm` 继续推理，直到不再有 `tool_calls`，路由到 `end`。

**验证（本地已自测）**：

```bash
mkdir -p /tmp/skills/demo/data && echo "hello world" > /tmp/skills/demo/data/a.txt
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' \
  -d '{"message":"读 data/a.txt 然后用一句话总结"}'
```

预期：`reply` 不再长期为空，能基于文件内容给出总结（例如「该文件包含一行文本：hello world」）。

**提交记录（补充说明）**：

- 提交：`f319b98`  
- 标题：`feat(M6): ToolNode 闭环 + route_after_llm 条件路由`  
- 详细变更：`routes.py`（新增路由函数）、`graph.py`（条件边 + tools 闭环）、`nodes.py`（ToolNode 挂载）；实现与指南 M6「ToolNode + tool_calls 循环」目标一致。

---

## 规划中里程碑（M7 起，摘要）

细节与文件分工以 [docs/agent_skills_build_guide.md](docs/agent_skills_build_guide.md) 为准；落地后把对应小节上移到「已完成」并补全路径与 `curl`/测试。

| 里程碑 | 目标摘要 |
|--------|----------|
| **M7** | `WorkspaceManager`：按 `session_id` 隔离目录、`resolve` 防逃逸；API 注入 `configurable`；各工具改走 manager。 |
| **M8** | `skills/` + `SkillsManager` + **`call_skill`**：加载 `SKILL.md` 正文（不直接执行）；系统提示注入技能元数据列表。 |
| **M9** | **`RunPyScript`**：沙箱内执行 `.py`，注入 `SESSION_ID` 等，回传 stdout/stderr/exit_code。 |
| **M10** | **FileStateStore**：按会话持久化 `messages`；`skip_inject_system` 与 `route_after_start`；多轮「记得上一轮」。 |
| **M11** | **`result_set` + `apply_result_set`**：非流式正式交卷；流式路径不绑该工具。 |
| **M12** | **PipelineService**：图跑后台 + SSE chunk **写 PG** + 队列广播；与长连接解耦。 |
| **M13** | **游标续读**：`after_seq` / `after_event_id` / `after_turn_id` 重连补流。 |
| **M14** | **`summary` 节点**：超长上下文压缩后再进 `llm`。 |
| **M15** | **MemPalace + Chroma**：跨会话语义召回；`mempalace_inject` 接入图。 |

---

## README 维护约定

- **已完成**：每攻下一个 M，在「已完成里程碑」中追加一节，格式与 **M0–M6** 一致（路径表、验证、与指南偏差说明）。  
- **规划中**：某 M 开工前可在上表改一两句范围；**验收通过后**将该行从「规划中」表删除或改为「✓ 已合并」，并把详细内容写进「已完成」。  
- 协作与 checkpoint 提交约定见根目录 [AGENTS.md](AGENTS.md)。

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

- 协作、checkpoint 与 **「进入下一阶段」须按指南分工贴全码**：根目录 [AGENTS.md](AGENTS.md) §5
- 里程碑与分工：`docs/agent_skills_build_guide.md`
- 协作与提交流程：根目录 [AGENTS.md](AGENTS.md)
- 四层架构与图节点：`docs/user_attachments_session_a29c06ca28284858b68f5de84ede3306_outputs_agent_skills_deep_research_report.md`
