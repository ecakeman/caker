# caker

在本地复现 [Agent Skills 跟写指南](docs/agent_skills_build_guide.md) 中的里程碑实现；架构说明见 [深度研究报告](docs/user_attachments_session_a29c06ca28284858b68f5de84ede3306_outputs_agent_skills_deep_research_report.md)。

**进度一览**：**M0–M9** 已在仓库落地（见下「已完成」各节）。**M10 及以后** 仅保留与指南对齐的**目标摘要**（本地路线 **M10–M11、M14–M15**，不含原 Pipeline / 游标两节）。某一 M 验收通过后，将对应小节改为与上文相同的「路径表 + 验证」写法。

---

## 已完成里程碑（M0–M9）

以下路径为**当前仓库已实现**内容。与指南骨架不一致处（如 `result` 而非 `result_text`、`inject_user` 节点）在各节单独说明。

### M0 项目脚手架

| 路径 | 说明 |
|------|------|
| [pyproject.toml](pyproject.toml) | 依赖与可编辑安装 |
| [app/main.py](app/main.py) | FastAPI 应用、`GET /health` |
| [app/config.py](app/config.py) | `pydantic-settings` 读 `.env`（`LLM_*`、`WORKSPACE_ROOT`、存储等） |
| [app/__init__.py](app/__init__.py) | 包初始化 |
| [.env.example](.env.example) | 环境变量模板 |
| [docker-compose.yaml](docker-compose.yaml) | 可选依赖（**M15 主要用 Chroma**；Postgres / MinIO 本地路线可不启） |
| [tests/test_m0_health.py](tests/test_m0_health.py) | `/health` 冒烟测试 |

**验证**：`curl -s http://127.0.0.1:8000/health` → `{"ok":true}`。

**启动服务**（在仓库根目录）：

```bash
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

注意模块写法是 **`app.main:app`**（点号），不是文件路径 `app/main:app`。

---

### M1 单轮 echo

| 路径 | 说明 |
|------|------|
| [app/api/chat.py](app/api/chat.py) | `APIRouter(prefix="/api/v2")`、`EchoIn` / `EchoOut`、`POST /echo`；`EchoIn` 含可选 `session_id`（M7 起复用同一字段语义） |
| [app/main.py](app/main.py) | `app.include_router(chat_router)` |

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
| [app/runtime/llm.py](app/runtime/llm.py) | `get_llm()`、`clear_llm_cache()`、`stream_messages()` |
| [app/api/chat.py](app/api/chat.py) | `ChatOnceIn` / `ChatOnceOut`、`POST /chat-once` |
| [.env.example](.env.example) | `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL_NAME`、`LLM_TEMPERATURE` |

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
| [app/runtime/state.py](app/runtime/state.py) | `GraphState`：`messages`（`add_messages`）、`input`、`result`、`skip_inject_system` |
| [app/runtime/nodes.py](app/runtime/nodes.py) | `start` → `inject_system` → `inject_user` → `llm` → `end` |
| [app/runtime/graph.py](app/runtime/graph.py) | `StateGraph`、`build_graph()`、`GRAPH` |
| [app/api/chat.py](app/api/chat.py) | `ChatGraphIn` / `ChatGraphOut`、`POST /chat-graph` |

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
| [app/runtime/sse.py](app/runtime/sse.py) | `sse_pack`、`sse_comment` |
| [app/runtime/graph.py](app/runtime/graph.py) | `iter_graph_stream_events` → `GRAPH.astream_events(..., version="v2")` |
| [app/runtime/nodes.py](app/runtime/nodes.py) | `llm_node` 使用 `await get_llm().ainvoke`（满足流式事件） |
| [app/api/chat.py](app/api/chat.py) | `POST /stream`、`StreamingResponse`；`event: delta` / `done` / `error` |

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
| [app/tools/__init__.py](app/tools/__init__.py) | 工具包 |
| [app/tools/base.py](app/tools/base.py) | `build_default_tools()` → `[ReadTool()]` |
| [app/tools/read_tool.py](app/tools/read_tool.py) | `Read` 工具定义 |
| [app/runtime/llm.py](app/runtime/llm.py) | `get_llm_with_tools(tools)` → `bind_tools` |
| [app/runtime/nodes.py](app/runtime/nodes.py) | `llm_node` 使用绑定工具的 LLM |

**阶段行为（M5 当时）**：仅 `bind_tools`，图内尚无 `ToolNode`，模型可能只返回 `tool_calls` 而无最终正文。**M6 已接入 ToolNode 闭环**（见下节）。

---

### M6 ToolNode + tool_calls 循环

| 路径 | 说明 |
|------|------|
| [app/runtime/routes.py](app/runtime/routes.py) | `route_after_llm`：有 `tool_calls` → `tools`，否则 → `end` |
| [app/runtime/graph.py](app/runtime/graph.py) | `tools` 节点；`llm` 条件边；`tools → llm` 回环 |
| [app/runtime/nodes.py](app/runtime/nodes.py) | `tools_node = ToolNode(_TOOLS)` |

**闭环**：`llm` 产出 `tool_calls` → `ToolNode` 执行 → `ToolMessage` 回灌 → 再进 `llm` → 无 `tool_calls` 时 `end`。

**验证**：

```bash
mkdir -p /tmp/skills/demo/data && echo "hello world" > /tmp/skills/demo/data/a.txt
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' \
  -d '{"message":"读 data/a.txt 然后用一句话总结"}'
```

---

### M7 Workspace 沙箱

| 路径 | 说明 |
|------|------|
| [app/workspace/__init__.py](app/workspace/__init__.py) | 工作区包（空文件即可） |
| [app/workspace/manager.py](app/workspace/manager.py) | `WorkspaceManager`：`session_dir`、`resolve`、`is_readonly`；模块级 `manager` 单例 |
| [app/tools/read_tool.py](app/tools/read_tool.py) | `Read` 经 `manager.resolve(session_id, rel_path)`；`session_id` 从 `run_manager.config["configurable"]` 读取 |
| [app/api/chat.py](app/api/chat.py) | `ChatGraphIn.session_id`；`_graph_config()`；`chat-graph` / `stream` 的 `ainvoke` / `astream_events` 传入 `config` |
| [app/runtime/graph.py](app/runtime/graph.py) | `iter_graph_stream_events(..., config=...)` 转发给 `astream_events` |

**行为要点**：

- 每个 `session_id` 对应 `WORKSPACE_ROOT/<session_id>/`，自动创建 `data/`、`outputs/`。
- `resolve` 拒绝绝对路径、`..` 越权；`session_id` 仅允许 `[A-Za-z0-9_-]+`。
- `is_readonly` 识别 `skills/`、`books/` 前缀（供后续写类工具使用）。
- 默认 `session_id` 为 `demo`（与演示数据路径一致）。

**验证**：

```bash
# 准备 demo 会话数据（路径与 .env 中 WORKSPACE_ROOT 一致，默认 /tmp/skills）
mkdir -p /tmp/skills/demo/data && echo "hello world" > /tmp/skills/demo/data/a.txt

# 正常读文件并总结
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' \
  -d '{"message":"读 data/a.txt 然后用一句话总结","session_id":"demo"}'

# 越权路径应被拒绝（模型侧说明无法读取，或工具返回 <error>）
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' \
  -d '{"message":"读 ../../../etc/passwd","session_id":"demo"}'
```

**本地验收记录（2026-05）**：`health` 200；`chat-graph` 能总结 `hello world`；越权请求未泄露 `/etc/passwd` 内容。

---

### M8 `call_skill` + SkillsManager

| 路径 | 说明 |
|------|------|
| [skills/hello_skill/SKILL.md](skills/hello_skill/SKILL.md) | 示例技能包（front matter + 操作说明） |
| [skills/hello_skill/run.py](skills/hello_skill/run.py) | 占位脚本（M9 执行） |
| [app/skills/manager.py](app/skills/manager.py) | 索引仓库根 `skills/*/SKILL.md`；`list_meta` / `load_body`（剥 front matter） |
| [app/tools/call_skill_tool.py](app/tools/call_skill_tool.py) | `call_skill` 返回 instructions JSON |
| [app/tools/base.py](app/tools/base.py) | `build_default_tools()` 注册 `Read` + `CallSkill` |
| [app/runtime/nodes.py](app/runtime/nodes.py) | 系统提示注入 `Available skills`（保留中文 Caker 人设） |

**行为要点**：

- 技能正文在 `call_skill` 时按需加载，系统提示只含元数据 JSON。
- `SkillsManager` 默认锚到仓库根 `skills/`，不依赖 uvicorn 工作目录。

**验证**：

```bash
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
| [app/tools/run_py_script_tool.py](app/tools/run_py_script_tool.py) | `RunPyScript`：子进程执行 `skills/**/*.py`，返回 `exit` / `stdout` / `stderr` |
| [app/tools/base.py](app/tools/base.py) | 注册 `RunPyScriptTool` |
| [app/workspace/manager.py](app/workspace/manager.py) | `session_dir` 内 `skills/` → 仓库根 `skills/` 的 symlink；`resolve` 对 `skills/` 不做 `resolve()` 越界误判 |

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

## 规划中里程碑（M10 起，摘要）

细节见 [docs/agent_skills_build_guide.md](docs/agent_skills_build_guide.md)（**本地部署**：M10 规划为 `AsyncSqliteSaver`；当前 **M9 运行时未接** checkpointer；SSE 单连接，不跟 Pipeline / 游标）。

| 里程碑 | 目标摘要 |
|--------|----------|
| **M10** | **AsyncSqliteSaver**（`var/state.db`）+ `thread_id`；`start` 条件边（有历史则 `start→inject_user`，跳过 `inject_system`） |
| **M11** | `result_set` + `apply_result_set`（非流式交卷） |
| **M14** | `summary` 节点：长上下文压缩（前置 M11） |
| **M15** | MemPalace + Chroma：跨会话语义记忆（前置 M14） |

---

## README 维护约定

- **已完成**：每攻下一个 M，在「已完成里程碑」追加一节（路径表、验证、与指南差异）。
- **规划中**：验收通过后从规划表移除，并写入「已完成」。
- 协作与 checkpoint： [AGENTS.md](AGENTS.md) §5。

---

## 快速开始

```bash
cd caker
cp .env.example .env
# 编辑 .env 填入 LLM_* 与 WORKSPACE_ROOT
python -m venv .venv && source .venv/bin/activate
pip install -e .
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

可选：`docker compose up -d chroma`（M15；Chroma 映射本机 **8001**）。Postgres / MinIO 本地路线可不启动。

---

## 文档依据

- 协作、checkpoint 与「进入下一阶段」贴码约定：[AGENTS.md](AGENTS.md) §5
- 里程碑与分工：[docs/agent_skills_build_guide.md](docs/agent_skills_build_guide.md)
- 四层架构：[docs/user_attachments_session_a29c06ca28284858b68f5de84ede3306_outputs_agent_skills_deep_research_report.md](docs/user_attachments_session_a29c06ca28284858b68f5de84ede3306_outputs_agent_skills_deep_research_report.md)
