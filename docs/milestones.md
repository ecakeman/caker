# 里程碑实现进度（M0–M13）

**只针对agent引擎开发**
本仓库相对 [跟写指南](agent_skills_build_guide.md) 的**已落地验收记录**。项目介绍见 [README](../README.md)。

**编号对照**：本表 **M12 = 指南 M14（summary/compact）**，**M13 = 指南 M15（MemPalace）**。

---

## 已完成里程碑（M0–M13）

以下路径为**当前仓库已实现**内容。与指南骨架不一致处（如 `result` 而非 `result_text`、`inject_user` 节点）在各节单独说明。

### M0 项目脚手架

| 路径 | 说明 |
|------|------|
| [pyproject.toml](../pyproject.toml) | 依赖与可编辑安装 |
| [app/main.py](../app/main.py) | FastAPI 应用、`GET /health` |
| [app/config.py](../app/config.py) | `pydantic-settings` 读 `.env`（`LLM_*`、`WORKSPACE_ROOT`、存储等） |
| [app/__init__.py](../app/__init__.py) | 包初始化 |
| [.env.example](../.env.example) | 环境变量模板（仅占位符；真实 `BASE_URL` / Key 只写在本地 `.env`） |
| [docker-compose.yaml](../docker-compose.yaml) | 可选依赖（**M13 主要用 Chroma**；Postgres / MinIO 本地路线可不启） |
| [tests/test_m0_health.py](../tests/test_m0_health.py) | `/health` 冒烟测试 |

**验证**：`curl -s http://127.0.0.1:8000/health` → `{"ok":true}`。

**安全**：`.env` 已在 `.gitignore`；仓库内仅保留占位符模板。若曾把真实 `LLM_BASE_URL` / Key 推送到远端，请在控制台轮换密钥，必要时清理 Git 历史。

**启动服务**（在仓库根目录）：

```bash
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

注意模块写法是 **`app.main:app`**（点号），不是文件路径 `app/main:app`。

---

### M1 单轮 echo

| 路径 | 说明 |
|------|------|
| [app/api/chat.py](../app/api/chat.py) | `APIRouter(prefix="/api/v2")`、`EchoIn` / `EchoOut`、`POST /echo`；`EchoIn` 含可选 `session_id`（M7 起复用同一字段语义） |
| [app/main.py](../app/main.py) | `app.include_router(chat_router)` |

**验证**：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v2/echo \
  -H 'content-type: application/json' \
  -d '{"message":"hi"}'
```

---

### M2 接 LLM（非流式）

| 路径 | 说明 |
|------|------|
| [app/runtime/llm.py](../app/runtime/llm.py) | `get_llm()`、`clear_llm_cache()`、`stream_messages()` |
| [app/api/chat.py](../app/api/chat.py) | `ChatOnceIn` / `ChatOnceOut`、`POST /chat-once` |
| [.env.example](../.env.example) | `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL_NAME`、`LLM_TEMPERATURE` |

**验证**：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-once \
  -H 'content-type: application/json' \
  -d '{"message":"用一句话介绍 LangGraph"}'
```

---

### M3 LangGraph 雏形

| 路径 | 说明 |
|------|------|
| [app/runtime/state.py](../app/runtime/state.py) | `GraphState`：`messages`（`add_messages`）、`input`、`result`、`skip_inject_system`（M11 起增 `result_set_handled`、`streaming`） |
| [app/runtime/nodes.py](../app/runtime/nodes.py) | `start` →（条件）`inject_system` / `inject_user` → `llm` → `end`（M10 条件边；M6 起含 `tools`） |
| [app/runtime/graph.py](../app/runtime/graph.py) | `StateGraph`、`build_graph()`、`GRAPH` |
| [app/api/chat.py](../app/api/chat.py) | `ChatGraphIn` / `ChatGraphOut`、`POST /chat-graph` |

**与指南差异**：首轮 `messages` 为空，用户句走 **`input`**，由 `inject_user_node` 写入 `HumanMessage`；聚合字段为 **`result`**（非 `result_text`）。

**验证**：

```bash
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' \
  -d '{"message":"hi"}'
```

---

### M4 SSE 流式输出

| 路径 | 说明 |
|------|------|
| [app/runtime/sse.py](../app/runtime/sse.py) | `sse_pack`、`sse_comment` |
| [app/runtime/graph.py](../app/runtime/graph.py) | `iter_graph_stream_events` → `GRAPH.astream_events(..., version="v2")` |
| [app/runtime/nodes.py](../app/runtime/nodes.py) | `llm_node` 使用 `await get_llm().ainvoke`（满足流式事件） |
| [app/api/chat.py](../app/api/chat.py) | `POST /stream`、`StreamingResponse`；`event: delta` / `done` / `error` |

**验证**：

```bash
curl -N -X POST http://127.0.0.1:8000/api/v2/stream \
  -H 'content-type: application/json' \
  -d '{"message":"数到5"}'
```

流式请求须打到**本机 caker**（如 `127.0.0.1:8000`），不要对上游 LLM 域名拼 `/api/v2/stream`。经 nginx 反代时需关 SSE 缓冲（`proxy_buffering off`）。

---

### M5 第一个 Tool：`Read`

| 路径 | 说明 |
|------|------|
| [app/tools/__init__.py](../app/tools/__init__.py) | 工具包 |
| [app/tools/base.py](../app/tools/base.py) | `build_default_tools()` → `[ReadTool()]` |
| [app/tools/read_tool.py](../app/tools/read_tool.py) | `Read` 工具定义 |
| [app/runtime/llm.py](../app/runtime/llm.py) | `get_llm_with_tools(tools)` → `bind_tools` |
| [app/runtime/nodes.py](../app/runtime/nodes.py) | `llm_node` 使用绑定工具的 LLM |

**阶段行为（M5 当时）**：仅 `bind_tools`，图内尚无 `ToolNode`，模型可能只返回 `tool_calls` 而无最终正文。**M6 已接入 ToolNode 闭环**（见下节）。

---

### M6 ToolNode + tool_calls 循环

| 路径 | 说明 |
|------|------|
| [app/runtime/routes.py](../app/runtime/routes.py) | `route_after_llm`：有 `tool_calls` → `tools`，否则 → `end` |
| [app/runtime/graph.py](../app/runtime/graph.py) | `tools` 节点；`llm` 条件边；`tools → llm` 回环 |
| [app/runtime/nodes.py](../app/runtime/nodes.py) | `tools_node = ToolNode(_TOOLS)` |

**闭环**：`llm` 产出 `tool_calls` → `ToolNode` 执行 → `ToolMessage` 回灌 → 再进 `llm` → 无 `tool_calls` 时 `end`。

**验证**：

```bash
mkdir -p var/workspace/local/demo/data && echo "hello world" > var/workspace/local/demo/data/a.txt
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' \
  -H 'x-user-id: local' \
  -d '{"message":"读 data/a.txt 然后用一句话总结","session_id":"demo"}'
```

---

### M7 Workspace 沙箱

| 路径 | 说明 |
|------|------|
| [app/workspace/__init__.py](../app/workspace/__init__.py) | 工作区包（空文件即可） |
| [app/workspace/manager.py](../app/workspace/manager.py) | `WorkspaceManager`：`session_dir(user_id, session_id)`、`resolve`、`remove_*`；模块级 `manager` 单例 |
| [app/tools/read_tool.py](../app/tools/read_tool.py) | `Read` 经 `manager.resolve(user_id, session_id, rel_path)`；ids 从 `configurable` 读取 |
| [app/api/chat.py](../app/api/chat.py) | `ChatGraphIn.session_id`；`_graph_config()`；`chat-graph` / `stream` 的 `ainvoke` / `astream_events` 传入 `config` |
| [app/runtime/graph.py](../app/runtime/graph.py) | `iter_graph_stream_events(..., config=...)` 转发给 `astream_events` |

**行为要点**：

- 每个会话对应 `WORKSPACE_ROOT/<user_id>/<session_id>/`，自动创建 `data/`、`outputs/`。
- `resolve` 拒绝绝对路径、`..` 越权；`session_id` 仅允许 `[A-Za-z0-9_-]+`。
- `is_readonly` 识别 `skills/`、`books/` 前缀（供后续写类工具使用）。
- 默认 `session_id` 为 `demo`（与演示数据路径一致）。

**验证**：

```bash
# 准备 demo 会话数据（默认 WORKSPACE_ROOT=./var/workspace）
mkdir -p var/workspace/local/demo/data && echo "hello world" > var/workspace/local/demo/data/a.txt

# 正常读文件并总结
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' \
  -H 'x-user-id: local' \
  -d '{"message":"读 data/a.txt 然后用一句话总结","session_id":"demo"}'

# 越权路径应被拒绝（模型侧说明无法读取，或工具返回 <error>）
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' \
  -d '{"message":"读 ../../../etc/passwd","session_id":"demo"}'
```

**本地验收记录（2026-05）**：`health` 200；`chat-graph` 能总结 `hello world`；越权请求未泄露 `/etc/passwd` 内容。

---

### M8 `call_skill` + SkillManager + 系统提示词

| 路径 | 说明 |
|------|------|
| [system_prompt.md](../system_prompt.md) | 系统提示词模板（`{skills_meta}` 占位）；`SkillManager.render_system_prompt()` 注入 |
| [skills/hello_skill/SKILL.md](../skills/hello_skill/SKILL.md) | 示例技能包（front matter + 操作说明） |
| [skills/hello_skill/run.py](../skills/hello_skill/run.py) | 占位脚本（M9 执行） |
| [app/skills/manager.py](../app/skills/manager.py) | 索引仓库根 `skills/*/SKILL.md`；`list_meta` / `load_body`（剥 front matter） |
| [app/tools/call_skill_tool.py](../app/tools/call_skill_tool.py) | `call_skill` 返回 instructions JSON |
| [app/tools/base.py](../app/tools/base.py) | `build_default_tools()` 注册 `Read` + `CallSkill` |
| [app/runtime/nodes.py](../app/runtime/nodes.py) | `inject_system_node` → `render_system_prompt()` 加载 [system_prompt.md](../system_prompt.md) |

**行为要点**：

- 技能正文在 `call_skill` 时按需加载，系统提示只含元数据 JSON。
- `SkillManager` 默认锚到仓库根 `skills/`，不依赖 uvicorn 工作目录。

**系统提示词维护**（面向开发者，不注入 LLM）：

| 项 | 说明 |
|----|------|
| 文件 | 仓库根 [system_prompt.md](../system_prompt.md)，与 `skills/` 平级；正文**仅**面向对话中的 Caker，不含部署说明 |
| 注入 | `inject_system_node()` → `skills_manager.render_system_prompt()` → `SystemMessage`；占位符 `{skills_meta}` 由 `list_meta()` 替换 |
| 与 [AGENTS.md](../AGENTS.md) | AGENTS 管协作与改仓库授权；system_prompt 管工具使用与工作区行为 |
| 修改后 | 编辑 `system_prompt.md` 并重启 uvicorn；已有 `thread_id` 的多轮会话仍保留首轮 SystemMessage（M10） |

**验证**：

```bash
uv run --extra dev pytest tests/test_system_prompt.py -q

curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' \
  -d '{"message":"用 hello_skill 跟我打个招呼","session_id":"demo"}'
```

预期：出现 `call_skill("hello_skill")`；M9 前可能对 `RunPyScript` 失败（正常）。

**提交**：`2a90ef4`。

---

### M9 `RunPyScript`

| 路径 | 说明 |
|------|------|
| [app/tools/run_py_script_tool.py](../app/tools/run_py_script_tool.py) | `RunPyScript`：子进程执行 `skills/**/*.py`，返回 `exit` / `stdout` / `stderr` |
| [app/tools/base.py](../app/tools/base.py) | 注册 `RunPyScriptTool` |
| [app/workspace/manager.py](../app/workspace/manager.py) | `session_dir` 内 `skills/` → 仓库根 `skills/` 的 symlink；`resolve` 对 `skills/` 不做 `resolve()` 越界误判 |

**行为要点**：

- `rel_path` 必须以 `skills/` 开头；`cwd` 为会话根 `WORKSPACE_ROOT/<session_id>/`。
- 环境变量：`SESSION_ID`、 `USER_ID=local`。
- 工具经 `app/tools/base.py` 注册，`nodes.py` 通过 `build_default_tools()` 使用（非在 `nodes.py` 内手写列表）。

**验证**：

```bash
# 单元：脚本可执行
uv run python -c "
from app.tools.run_py_script_tool import RunPyScriptTool
import json
class RM:
    config = {'configurable': {'session_id': 'demo'}}
print(json.loads(RunPyScriptTool()._run('skills/hello_skill/run.py', run_manager=RM())))
"

# 端到端
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' \
  -d '{"message":"用 hello_skill 打个招呼","session_id":"demo"}'
```

预期：`RunPyScript` 的 `stdout` 含 `hello, world`（或模型在 `reply` 中转述）；`exit` 为 0。

**提交**：`5f86823`。

---

### M10 多轮历史（AsyncSqliteSaver）

| 路径 | 说明 |
|------|------|
| [app/main.py](../app/main.py) | FastAPI `lifespan`：`AsyncSqliteSaver` + `setup()` + `compile_graph` |
| [app/runtime/graph.py](../app/runtime/graph.py) | `start` 条件边；`compile_graph` / `get_graph` |
| [app/runtime/routes.py](../app/runtime/routes.py) | `route_after_start` |
| [app/runtime/nodes.py](../app/runtime/nodes.py) | `start_node` 按恢复后的 `messages` 设 `skip_inject_system` |
| [app/api/chat.py](../app/api/chat.py) | `thread_id` + `session_id`；`get_graph().ainvoke` |

**行为要点**：

- 检查点写入 `var/state.db`（`.gitignore`）；须 **`AsyncSqliteSaver`**，与 `ainvoke` 配套。
- 每轮 API 仍传 `messages: []`；历史由 `thread_id` 从 SQLite 恢复；次轮起跳过 `inject_system`。

**验证**：

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

SID=demo-m10-$(date +%s)
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' \
  -d "{\"message\":\"我叫张三\",\"session_id\":\"$SID\"}"
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' \
  -d "{\"message\":\"我叫什么？\",\"session_id\":\"$SID\"}"
```

预期：第二条能答「张三」；重启 uvicorn 后同 `session_id` 仍可延续。

---

### M11 `result_set` + `apply_result_set`

| 路径 | 说明 |
|------|------|
| [app/tools/result_set_tool.py](../app/tools/result_set_tool.py) | `result_set(text)` 交卷工具 |
| [app/tools/base.py](../app/tools/base.py) | `build_default_tools(include_result_set=...)` |
| [app/runtime/llm.py](../app/runtime/llm.py) | `get_tools_for_state(streaming=...)` |
| [app/runtime/nodes.py](../app/runtime/nodes.py) | `apply_result_set_node`；`llm_node` 按 `streaming` 绑工具 |
| [app/runtime/routes.py](../app/runtime/routes.py) | `route_after_tools` → `end` / `summary` / `llm` |
| [app/runtime/graph.py](../app/runtime/graph.py) | `tools` → `apply_result_set` → 条件边 |
| [app/api/chat.py](../app/api/chat.py) | `/chat-graph`：`streaming=False`；`/stream`：`streaming=True` |
| [system_prompt.md](../system_prompt.md) | 增加 `result_set` 工具说明 |

**行为要点**：

- 非流式：`result_set` 写入 `state["result"]` 后直达 `end`；流式不绑该工具。
- `apply_result_set` 只改 `result` 与标志位，不追加 `messages`。

**验证**：

```bash
mkdir -p var/workspace/local/demo-m11/data && echo "hello world" > var/workspace/local/demo-m11/data/a.txt
uv run --extra dev pytest tests/test_m11_result_set.py -q

curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' \
  -H 'x-user-id: local' \
  -d '{"message":"读 data/a.txt 然后用 result_set 给我最终答案","session_id":"demo-m11"}'
```

---

### M12 `summary`（长上下文压缩）

| 路径 | 说明 |
|------|------|
| [app/summary/handler.py](../app/summary/handler.py) | `tiktoken` 估算；`need_summary` / `summarize` |
| [app/runtime/nodes.py](../app/runtime/nodes.py) | `summary_node`：`RemoveMessage` + 摘要 + 本轮 `input` |
| [app/runtime/routes.py](../app/runtime/routes.py) | `route_after_tools` 超阈值 → `summary` |
| [app/runtime/graph.py](../app/runtime/graph.py) | `summary` → `llm` |

**行为要点**：

- 触发：`estimate_tokens(messages) >= MAX_INPUT_TOKENS * SUMMARY_COND_RATIO`（默认 8000×0.6）。
- 在 `apply_result_set` 之后、`llm` 之前；已 `result_set_handled` 时直接 `end`。
- 摘要会丢失工具中间细节，只保留对话级语义。

**验证**：

```bash
uv run --extra dev pytest tests/test_m14_summary.py -q
uv run python -c "from app.runtime.graph import build_graph; g=build_graph(); print('summary' in g.nodes)"
```

---

### M13 MemPalace（跨会话语义记忆）

| 路径 | 说明 |
|------|------|
| [app/mempalace/chroma_store.py](../app/mempalace/chroma_store.py) | `PersistentClient`（`CHROMA_PATH`）；`OpenAIEmbeddingFunction`；`add` / `search` |
| [app/mempalace/injector.py](../app/mempalace/injector.py) | `should_inject`、`build_bootstrap`（JSON `HumanMessage`） |
| [app/mempalace/__init__.py](../app/mempalace/__init__.py) | 包初始化 |
| [app/config.py](../app/config.py) | `embedding_*`、`chroma_path` |
| [.env.example](../.env.example) | `EMBEDDING_MODEL_NAME` / `EMBEDDING_BASE_URL` / `EMBEDDING_API_KEY` / `EMBEDDING_DIMENSIONS` |
| [app/runtime/nodes.py](../app/runtime/nodes.py) | `mempalace_inject_node`；`end_node` 写入 Chroma |
| [app/runtime/graph.py](../app/runtime/graph.py) | `inject_user` → `mempalace_inject` → `llm` |
| [app/api/chat.py](../app/api/chat.py) | 请求头 `x-user-id` → `configurable.user_id`（`chat-graph` / `stream`） |
| [tests/test_m13_mempalace.py](../tests/test_m13_mempalace.py) | 注入条件与节点单测 |

**行为要点**：

- **写入**：每轮 `end_node` 对当前 `messages` 做 `summarize()`，以 UUID 为 id upsert 到 collection `mempalace`，元数据含 `session_id`、`user_id`。
- **召回**：每轮用户句注入后、`llm` 前执行 `mempalace_inject`；按 `user_id` 过滤向量检索，命中则插入一条 `{"mempalace": true, "wakeup", "recall": [...]}` 的 `HumanMessage`（同轮不重复注入）。
- **嵌入**：走 **OpenAI 兼容 Embedding API**（见 `.env` 的 `EMBEDDING_*`），**不**下载本地 `all-MiniLM-L6-v2`。若曾用默认嵌入建过库，首次切换会自动删旧 collection 重建。
- **与 M10 区别**：M10 同 `session_id` 的多轮在 SQLite；M13 同 **`user_id`**、不同 `session_id` 可跨会话召回。
- **可选**：`docker compose up -d chroma` 为独立 Chroma 服务（端口 8001）；当前实现默认 **进程内** `PersistentClient` 写 `./var/chroma`，可不启 compose。

**与指南差异**：指南称 M15；本仓库 README 序号为 M13。未实现 L0 结构化 JSON 文件（指南可选练手项）。

**验证**：

```bash
uv run --extra dev pytest tests/test_m13_mempalace.py -q

# 需在 .env 配置 EMBEDDING_*（见 .env.example）
USER=u-demo
SID1=mp1-$(date +%s)
SID2=mp2-$(date +%s)

curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' -H "x-user-id: $USER" \
  -d "{\"message\":\"我家猫叫小酥，是灰色的。只回复：好的\",\"session_id\":\"$SID1\"}"

sleep 2

curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' -H "x-user-id: $USER" \
  -d "{\"message\":\"我家猫是什么颜色的？\",\"session_id\":\"$SID2\"}"
```

预期：第二次 `reply` 能提到灰色/小酥（依赖召回与模型采信软上下文）。

**提交**：`b279bee`。

---

## 维护约定

- **已完成**：每攻下一个 M，在本文「已完成里程碑」追加一节（路径表、验证、与指南差异）。
- **规划中**：验收通过后从规划表移除，并写入「已完成」。
- 协作与 checkpoint：[AGENTS.md](../AGENTS.md) §5。

