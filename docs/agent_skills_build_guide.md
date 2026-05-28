# Agent 引擎 跟写指南（Build-along）

> 用法：每个里程碑 M# 都能跑出来一个比上一个强一点点的 demo；不绿就别往下走。

### 本地部署范围（caker 默认）

本仓库跟写路线面向**单机本地开发**，不实现原报告中的分布式能力：

| 能力 | 本地路线 | 原报告 / 生产向 |
|------|----------|-----------------|
| 多轮历史 | M10：`AsyncSqliteSaver`（`var/state.db`）+ `thread_id` | S3 / PG checkpoint、`FileStateStore` |
| SSE 流式 | M4：请求内 `astream_events`（单连接） | M12 `PipelineService` + PG chunk 日志 |
| 断线续传 | **不做** | M13 游标 `after_seq` 等 |
| 向量记忆 | M15：Chroma（`CHROMA_PATH` 或 compose） | 同左，可换托管向量库 |

里程碑 **M0–M11、M14–M15** 跟完即可跑通本地 Agent；**不跟**原指南中的 Pipeline / 游标两节（下文已删）。

### caker 仓库约定（与下文骨架的差异）

跟写 **本仓库（caker）** 时，以下约定优先于各节里较早的通用骨架；各 M 节末尾也会用 **「caker」** 标注要点。

| 主题 | 通用骨架 / 原报告 | **caker 现状** |
|------|-------------------|----------------|
| 状态字段 | `result_text` | **`result`**；用户句走 **`input`** + **`inject_user_node`**（非把 HumanMessage 塞进首轮 `messages`） |
| 工具注册 | 各节在 `nodes.py` 里写 `_TOOLS = [...]` | **`app/tools/base.py`** 的 `build_default_tools()`；`nodes.py` 仅 `_TOOLS = build_default_tools()` |
| 技能包路径 | 有时写 cwd 相对 `skills/` | 仓库根 **`skills/`**（`app/skills/manager.py` 锚到仓库根索引 SKILL.md） |
| 配置 / `.env` | `OPENAI_*` | **`LLM_*`** → `settings.llm_*`（见 §1） |
| 图执行 API | — | FastAPI 用 **`await GRAPH.ainvoke` / `astream_events`**（异步） |
| M7 工作区 | `skills/` symlink「可选」 | M7 可不做；**M9 起在 caker 中为必需**（见 M9） |
| M8 系统提示 | 纯英文 Agent / 硬编码在 `nodes.py` | 仓库根 **`system_prompt.md`** + `SkillManager.render_system_prompt()`；`{skills_meta}` 动态注入；正文仅面向 LLM（维护说明见 README） |
| M10 检查点 | 文中示例同步 `SqliteSaver` | **`AsyncSqliteSaver`**（`var/state.db`）+ FastAPI `lifespan`；须与 **`ainvoke`** 配套（见 M10） |

---

## 0. 怎么用这本指南

### 三种分工标签

| 标签 | 含义 |
|------|------|
| `[你手敲]` | 核心练习。**不要让我写**，敲完你才会真懂。 |
| `[我写]` | 样板/重复劳动。让我贴模板即可。 |
| `[一起写]` | 我给骨架 + `# TODO` 注释，你填关键逻辑。 |

### 每个里程碑统一模板
1. **目标**：跑起来能干嘛。
2. **前置**：依赖哪个 M 的产物。
3. **文件清单与分工**：要新增/修改哪些文件，每个标签。
4. **关键代码骨架**：贴最少必要片段，留 `# TODO`。
5. **验证**：一行命令验绿。
6. **易错点**：踩过的具体错误信息。
7. **对应原报告**：可以回去对读哪一节。

---

## 1. 技术选型（与原报告对齐）

| 维度 | 选型 | 备注 |
|------|------|------|
| Web | FastAPI + uvicorn | 中间件、SSE 都靠它 |
| Agent 编排 | LangGraph (`langgraph`) | StateGraph、MessagesState、ToolNode |
| LLM 客户端 | `langchain-openai`（OpenAI 兼容） | base_url 可指向自部署网关 |
| 检查点 | LangGraph **`AsyncSqliteSaver`**（M10，`var/state.db`） | 本地文件持久化；须与 **`ainvoke`** 配套（见 M10） |
| 关系库 | PostgreSQL 14+ | **可选**；本地路线不用（compose 中可不开） |
| 对象存储 | S3 / MinIO | **可选**；本地路线不用 |
| 向量库 | ChromaDB | MemPalace（M15）；可用 `CHROMA_PATH` 嵌入式，不必起 PG |
| 子进程脚本 | Python 3.11 + Node.js 20 | `RunPyScript`、`RunJsTsScript` |

环境变量（与仓库 [`.env.example`](../.env.example) 一致，OpenAI **兼容**网关通用）：

```bash
LLM_MODEL_NAME=gpt-4o-mini
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_TEMPERATURE=0.7

WORKSPACE_ROOT=/tmp/skills
# 以下 PG / S3 本地路线可留空；需要 docker compose 做 M15 时只起 chroma 即可
# PG_DSN=
# S3_ENDPOINT=
# S3_BUCKET=
CHROMA_PATH=./var/chroma
```

> `app/config.py` 字段名为 `llm_model_name` / `llm_base_url` / `llm_api_key`（无 `OPENAI_*` alias）。PAI-EAS、DashScope 等只需改 `LLM_BASE_URL` 与 `LLM_API_KEY`。

---

## 2. 项目骨架（M0 之前先建好）

下图以 **`caker` 仓库根** 为准（早期草稿曾写 `mini_skills/` 包裹目录，**实际仓库没有这一层**）。

```
caker/                            # 仓库根 = 你 clone 下来的目录
├── pyproject.toml
├── .env.example                  # LLM_* / WORKSPACE_ROOT / CHROMA_PATH
├── docker-compose.yaml           # 本地默认只需 Chroma（PG/MinIO 可选）
├── README.md
├── system_prompt.md              # M8+：系统提示词模板（{skills_meta} 占位）
├── var/                          # M10 起：state.db（.gitignore）
├── app/
│   ├── __init__.py
│   ├── main.py                   # M0：FastAPI + /health
│   ├── config.py                 # M0：pydantic-settings
│   ├── api/
│   │   ├── __init__.py
│   │   └── chat.py               # M1+：/echo、/chat-once、/chat-graph、/stream
│   ├── runtime/
│   │   ├── __init__.py
│   │   ├── state.py              # M3
│   │   ├── nodes.py              # M3+
│   │   ├── routes.py             # M6+（M10 增 route_after_start）
│   │   ├── graph.py              # M3+（M10 接 AsyncSqliteSaver）
│   │   ├── llm.py                # M2
│   │   └── sse.py                # M4
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py               # M5+ build_default_tools()（caker 统一注册工具）
│   │   ├── read_tool.py          # M5 ✅
│   │   ├── call_skill_tool.py    # M8
│   │   ├── run_py_script_tool.py # M9
│   │   ├── write_tool.py         # 原报告；本地路线未跟写
│   │   ├── edit_tool.py          # 原报告；本地路线未跟写
│   │   └── bash_tool.py          # 原报告；本地路线未跟写
│   ├── workspace/                # M7 ✅
│   │   ├── __init__.py
│   │   └── manager.py
│   ├── skills/                   # M8
│   │   ├── __init__.py
│   │   └── manager.py
│   ├── pipeline/                 # 原报告 §6；本地路线 **不创建**（已删 M12–M13 跟写）
│   ├── state_store/              # 原报告 §7；本地 M10 用 AsyncSqliteSaver，**不创建**
│   ├── summary/                  # M14
│   │   └── handler.py
│   └── mempalace/               # M15
│       ├── __init__.py
│       ├── chroma_store.py
│       └── injector.py
├── skills/                       # 仓库根：SKILL.md 包（非 app/skills）
│   └── hello_skill/
│       ├── SKILL.md
│       └── run.py
└── tests/
    ├── test_m0_health.py
    ├── test_m3_graph.py
    ...
```

**图例**

| 标记 | 含义 |
|------|------|
| `M# ✅` | 该里程碑在 caker 主线已落地（以 README「已完成」为准） |
| `M#` | 跟写目标，尚未实现或进行中 |
| **不创建** | 原报告有、本地路线故意跳过（勿照抄建目录） |

> 不必一次建全树；每个 M 只新增当节「文件清单」中的路径。

---

## M0 项目脚手架

### 目标
`uvicorn app.main:app --reload` 起来，访问 `GET /health` 返回 `{"ok": true}`。

### 前置
无。

### 文件清单与分工

| 文件 | 分工 | 说明 |
|------|------|------|
| `pyproject.toml` | `[我写]` | 锁依赖：fastapi/uvicorn/pydantic-settings/langgraph/langchain-openai/asyncpg/boto3/chromadb |
| `app/config.py` | `[我写]` | pydantic-settings 读 `.env` |
| `app/main.py` | `[一起写]` | 我给 FastAPI app + `/health`，你加日志/中间件 |
| `.env.example` | `[我写]` | 上节环境变量 |
| `docker-compose.yaml` | `[我写]` | postgres + minio + chroma |

### 关键代码骨架

```python
# app/config.py  [我写]（与当前 caker 仓库一致）
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_model_name: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    workspace_root: str = Field(default="/tmp/skills")
    pg_dsn: str = ""
    chroma_path: str = Field(default="./var/chroma")

settings = Settings()
```

```python
# app/main.py  [一起写]
from fastapi import FastAPI

app = FastAPI(title="caker")

@app.get("/health")
async def health():
    return {"ok": True}

# TODO: 你加 request_id 中间件、structlog 日志
```

### 验证
```bash
uvicorn app.main:app --reload
curl -s http://127.0.0.1:8000/health
```

### 易错点
- `pydantic-settings` 没装：`ModuleNotFoundError: pydantic_settings`。
- `.env` 不在 cwd 不会被读到——用绝对路径或在脚本入口 `os.chdir`。

### 对应原报告
§2 第一层（核心运行时）。

---

## M1 单轮 echo

### 目标
`POST /api/v2/echo` 收到 `{"message": "hi"}` 返 `{"reply": "you said hi"}`。

### 前置
M0。

### 文件清单与分工

| 文件 | 分工 |
|------|------|
| `app/api/chat.py` | `[你手敲]`（练 FastAPI Router + Pydantic schema） |
| `app/main.py` | `[一起写]`（include_router） |

### 关键代码骨架

```python
# app/api/chat.py  [你手敲]
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v2")

class EchoIn(BaseModel):
    message: str
    session_id: str | None = None

class EchoOut(BaseModel):
    reply: str

# TODO: 实现 @router.post("/echo")，返回 "you said {message}"
```

### 验证
```bash
curl -s -X POST http://127.0.0.1:8000/api/v2/echo \
  -H 'content-type: application/json' \
  -d '{"message":"hi"}'
# {"reply":"you said hi"}
```

### 易错点
- `include_router` 顺序：路由没生效多半是 `app.include_router(router)` 没加。

### 对应原报告
§2 第一层（FastAPI 接入层 514 行的最小子集）。

---

## M2 接 LLM（非流式）

### 目标
`POST /api/v2/chat-once`：拿到一条 user message，调一次 LLM，返回完整回复字符串。

### 前置
M1，且 `.env` 中 `LLM_API_KEY` / `LLM_MODEL_NAME` / `LLM_BASE_URL` 已配置。

### 文件清单与分工

| 文件 | 分工 |
|------|------|
| `app/runtime/llm.py` | `[我写]` 包装 `ChatOpenAI` 单例 |
| `app/api/chat.py` | `[你手敲]` 加 `chat-once` 路由 |

### 关键代码骨架

```python
# app/runtime/llm.py  [我写]
from functools import lru_cache
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from app.config import settings

@lru_cache(maxsize=8)
def get_llm(model: str | None = None) -> BaseChatModel:
    return ChatOpenAI(
        model=model or settings.llm_model_name,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=settings.llm_temperature,
    )
```

```python
# app/api/chat.py 增量  [你手敲]
from langchain_core.messages import HumanMessage
from app.runtime.llm import get_llm

class ChatOnceIn(BaseModel):
    message: str

class ChatOnceOut(BaseModel):
    reply: str

# TODO: @router.post("/chat-once")
#   1. llm = get_llm()
#   2. ai_msg = llm.invoke([HumanMessage(content=body.message)])
#   3. return {"reply": ai_msg.content}
```

### 验证
```bash
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-once \
  -H 'content-type: application/json' \
  -d '{"message":"用一句话介绍 LangGraph"}'
```

### 易错点
- 走自家网关时 `base_url` 必须以 `/v1` 结尾，并启用 OpenAI 兼容协议。
- `temperature` 给 chat 模型，给 reasoning 模型会被忽略；先用 `gpt-4o-mini` 这类 chat 模型。

### 对应原报告
§3 节点 4（LLM）「多模型动态切换 / 流式与非流式区分」。

---

## M3 LangGraph 雏形：start → llm → end

### 目标
把 M2 改写成图：`start → llm → end`。`POST /api/v2/chat-graph` 走图执行。

### 前置
M2。

### 文件清单与分工

| 文件 | 分工 |
|------|------|
| `app/runtime/state.py` | `[你手敲]` State TypedDict |
| `app/runtime/nodes.py` | `[你手敲]` `_start_node` `_llm_node` `_end_node` |
| `app/runtime/graph.py` | `[你手敲]` 用 StateGraph 拼图，编译 |
| `app/api/chat.py` | `[一起写]` 接通新路由 |

### 关键代码骨架

```python
# app/runtime/state.py  [你手敲]
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class GraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    input: str                      # 本轮用户句（caker：由 inject_user_node 写入 messages）
    result: str                     # 聚合回复（caker 不用 result_text）
    skip_inject_system: bool        # M10 起使用；M3–M9 先恒为 False
```

```python
# app/runtime/nodes.py  [你手敲] —— 核心练习
# TODO: async def start_node(state): return {}
# TODO: def inject_system_node(state): return {"messages": [SystemMessage(...)]}
# TODO: def inject_user_node(state): return {"messages": [HumanMessage(content=state["input"])]}
# TODO: async def llm_node(state): ai = await get_llm().ainvoke(...); return {"messages": [ai]}
# TODO: async def end_node(state): 从 messages 取最后 AIMessage → return {"result": ...}
```

```python
# app/runtime/graph.py  [你手敲]（caker 最小图含 inject_user）
    g.add_edge("start", "inject_system")
    g.add_edge("inject_system", "inject_user")
    g.add_edge("inject_user", "llm")
    g.add_edge("llm", "end")
```

**caker**：`chat-graph` 的 `ainvoke` 输入为 `messages: []`、`input: body.message`、`result: ""`，见 M7。

### 验证
```bash
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' \
  -d '{"message":"hi"}'
```
预期：返回 `{"reply": "...AI 文本..."}`。

### 易错点
- `add_messages` 必须用 `Annotated` 标注，否则消息会被覆盖而不是追加。
- 节点同步/异步混用没问题，但**编译后**不能在节点里直接 `await llm.invoke`（`invoke` 是同步），异步要用 `await llm.ainvoke`。

### 对应原报告
§3 节点 1/2/4/8 的最小子集；§9.1「图引擎即编排器」。

---

---

## M4 SSE 流式输出

### 目标
新增 `POST /api/v2/stream`：服务端用 SSE 把 LLM 输出**逐 chunk** 推给前端；`curl -N` 看到流式效果。

### 前置
M3。

### 文件清单与分工

| 文件 | 分工 |
|------|------|
| `app/runtime/sse.py` | `[我写]` SSE 帧封装（事件名、data、heartbeat） |
| `app/runtime/llm.py` | `[一起写]` 增加 `stream_messages` 适配 `astream` |
| `app/runtime/graph.py` | `[你手敲]` 用 `graph.astream_events` 逐事件吐 |
| `app/api/chat.py` | `[一起写]` 加 `/stream` 路由 + `StreamingResponse` |

### 关键代码骨架

```python
# app/runtime/sse.py  [我写]
import json
from typing import Any

def sse_pack(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")
```

```python
# app/api/chat.py 增量  [一起写]
from fastapi.responses import StreamingResponse
from app.runtime.graph import GRAPH
from app.runtime.sse import sse_pack
from langchain_core.messages import HumanMessage

@router.post("/stream")
async def stream_chat(body: EchoIn):
    async def gen():
        inputs = {
            "messages": [],
            "input": body.message,
            "result": "",
            "skip_inject_system": False,
        }
        # caker：与 chat-graph 相同，走 inject_user；勿把 HumanMessage 直接塞进 messages
        # TODO: 用 GRAPH.astream_events(inputs, version="v2")
        # 把 on_chat_model_stream 的 token 拼成 SSE event=delta
        # 最后吐 event=done
        yield sse_pack("hello", {"ok": True})
    return StreamingResponse(gen(), media_type="text/event-stream")
```

### 验证
```bash
curl -N -X POST http://127.0.0.1:8000/api/v2/stream \
  -H 'content-type: application/json' \
  -d '{"message":"数到5"}'
```
预期：终端逐个 `event: delta` 跳出来，最后一个 `event: done`。

### 易错点
- 反向代理（nginx/网关）会缓冲 SSE，必须显式关 `proxy_buffering off`。
- `astream_events` 要求图里的 LLM 节点用 **`ainvoke`/`astream`**，不能再用同步 `invoke`。
- `text/event-stream` 必须 `\n\n` 结尾，少一个换行前端就一直等。

### 对应原报告
§3 节点 4 流式区分。本地路线：**单连接 SSE 即可**；原报告 §6 Pipeline 解耦不在本仓库跟写。

---

## M5 第一个 Tool：`Read`

### 目标
让模型能调用 `Read` 工具读 `WORKSPACE_ROOT/<session_id>/` 下的文件。

### 前置
M3（流式可暂时不用）。

### 文件清单与分工

| 文件 | 分工 |
|------|------|
| `app/tools/base.py` | `[我写]` Tool 注册表（按名取实例） |
| `app/tools/read_tool.py` | `[你手敲]` 继承 `BaseTool`，实现 `_run` |
| `app/runtime/llm.py` | `[一起写]` 加 `get_llm_with_tools(tools)` 用 `bind_tools` |
| `app/runtime/nodes.py` | `[一起写]` `llm_node` 改用绑定工具的 LLM |

### 关键代码骨架

```python
# app/tools/read_tool.py  [你手敲]
from pathlib import Path
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from app.config import settings

class ReadInput(BaseModel):
    rel_path: str = Field(..., description="工作区相对路径")
    offset: int = 0
    limit: int = 200

class ReadTool(BaseTool):
    name: str = "Read"
    description: str = "Read a file from current session workspace"
    args_schema: type[BaseModel] = ReadInput

    def _run(self, rel_path: str, offset: int = 0, limit: int = 200,
             *, run_manager=None, **_) -> str:
        # TODO:
        # 1. 从 RunnableConfig 拿 session_id（可先固定 "demo"）
        # 2. 拼 ws = Path(settings.workspace_root)/session_id
        # 3. 拼 target = (ws/rel_path).resolve()
        # 4. 校验 target 在 ws 之内（防 ..）
        # 5. 按行读 offset~offset+limit
        # 6. 返回带行号的字符串
        ...
```

```python
# app/runtime/llm.py 增量  [一起写]
def get_llm_with_tools(tools):
    return get_llm().bind_tools(tools)
```

```python
# app/tools/base.py  [一起写]（caker：工具集中注册）
def build_default_tools() -> list[BaseTool]:
    return [ReadTool()]

# app/runtime/nodes.py  [一起写]
from app.tools.base import build_default_tools
_TOOLS = build_default_tools()

async def llm_node(state, config):
    llm = get_llm_with_tools(_TOOLS)
    ai = await llm.ainvoke(state["messages"])
    return {"messages": [ai]}
```

> ⚠️ 这一步图里**还没接 ToolNode**，模型若返回 `tool_calls` 你会看到一个空回答 + 一段工具调用 JSON。这是正常的，M6 才开始处理。

### 验证
```bash
mkdir -p /tmp/skills/demo/data && echo "hello world" > /tmp/skills/demo/data/a.txt
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' \
  -d '{"message":"请用 Read 工具读 data/a.txt 的前 100 行"}'
```
预期：返回的 `messages` 末尾 AIMessage 含 `tool_calls=[{name:"Read", args:{...}}]`。

### 易错点
- `args_schema` 字段名必须和 `_run` 形参一一对应，模型会按 schema 出参数。
- `description` 写得越准确越好；糊弄一句模型就不调用了。

### 对应原报告
§4 工具分类清单 — 文件系统组；§5 Workspace 安全约束（M7 详细做）。

---

## M6 ToolNode + tool_calls 循环

### 目标
模型可以发起 `Read`，框架自动执行并把结果回灌，模型再用结果继续回答。

### 前置
M5。

### 文件清单与分工

| 文件 | 分工 |
|------|------|
| `app/runtime/routes.py` | `[你手敲]` `_route_after_llm` 条件路由 |
| `app/runtime/graph.py` | `[你手敲]` 加 `tools` 节点和条件边 |
| `app/tools/base.py` | `[一起写]` `build_default_tools()` 含 `ReadTool` |
| `app/runtime/nodes.py` | `[一起写]` `_TOOLS = build_default_tools()`；`tools_node = ToolNode(_TOOLS)` |

### 关键代码骨架

```python
# app/runtime/routes.py  [你手敲]
from langchain_core.messages import AIMessage

def route_after_llm(state) -> str:
    last = state["messages"][-1]
    # TODO:
    # 1. 若 isinstance(last, AIMessage) 且 last.tool_calls 非空 -> "tools"
    # 2. 否则 -> "end"
    ...
```

```python
# app/runtime/graph.py  [你手敲] 增量
from langgraph.prebuilt import ToolNode
from app.runtime.routes import route_after_llm

def build_graph():
    g = StateGraph(GraphState)
    g.add_node("start", nodes.start_node)
    g.add_node("inject_system", nodes.inject_system_node)
    g.add_node("llm", nodes.llm_node)
    g.add_node("tools", nodes.tools_node)   # caker：在 nodes.py 定义 ToolNode(_TOOLS)
    g.add_node("end", nodes.end_node)

    g.add_edge(START, "start")
    g.add_edge("start", "inject_system")
    g.add_edge("inject_system", "inject_user")   # caker
    g.add_edge("inject_user", "llm")
    g.add_conditional_edges("llm", route_after_llm,
                            {"tools": "tools", "end": "end"})
    g.add_edge("tools", "llm")        # 工具回到 llm 继续推理
    g.add_edge("end", END)
    return g.compile()
```

### 验证
```bash
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -d '{"message":"读 data/a.txt 然后用一句话总结"}' \
  -H 'content-type: application/json'
```
预期：最终 `reply` 中含 `hello world` 的中文/英文摘要。

### 易错点
- `ToolNode` 期望最后一条是 `AIMessage` 且带 `tool_calls`；如果你在 `llm_node` 不小心追加了 `HumanMessage`，会报 `ValueError: Last message is not an AIMessage with tool_calls`。
- 工具内部抛异常 `ToolNode` 会塞 `ToolMessage(content="<error>...")`，不会中断图——便于调试，但也容易掩盖 bug。临时调试时可在 `_run` 里 `print(traceback)`。

### 对应原报告
§3 节点 5 + 路由 `_route_after_tools`/`_route_after_llm`。

---

## M7 Workspace 沙箱

### 目标
- 给每个 session 分一个目录。
- 所有 Tool 都过 `resolve_workspace_path()`：禁绝对路径、禁 `..`、`skills/` 只读。

### 前置
M6。

### 文件清单与分工

| 文件 | 分工 |
|------|------|
| `app/workspace/manager.py` | `[你手敲]` `WorkspaceManager` 三件套 |
| `app/tools/read_tool.py` 等 | `[一起写]` 改为调 `manager.resolve(...)` |
| `app/api/chat.py` | `[一起写]` 路由收 `session_id`，注入到 LangGraph `config["configurable"]` |

### 关键代码骨架

```python
# app/workspace/manager.py  [你手敲]
from pathlib import Path
from app.config import settings

READONLY_SUBDIRS = {"skills", "books"}

class WorkspaceError(Exception): ...

class WorkspaceManager:
    def __init__(self, root: str | None = None):
        self.root = Path(root or settings.workspace_root).resolve()

    def session_dir(self, session_id: str) -> Path:
        # TODO:
        # 1. 检查 session_id 合法（只允许 [A-Za-z0-9_-]）
        # 2. 路径 = self.root / session_id
        # 3. mkdir(parents=True, exist_ok=True)
        # 4. 创建 outputs/、data/ 子目录（读写）
        # 5. symlink skills/ → 仓库根 skills/（caker：M7 可省略，M9 必需，见 M9）
        ...

    def resolve(self, session_id: str, rel_path: str) -> Path:
        # TODO:
        # 1. 拒绝绝对路径 / 含 ".." 的 rel_path
        # 2. ws = self.session_dir(session_id)
        # 3. target = (ws / rel_path).resolve()
        # 4. 若 target 不在 ws 之下 -> WorkspaceError
        # 5. 返回 target
        ...

    def is_readonly(self, session_id: str, target: Path) -> bool:
        # TODO: target 相对 session_dir 的第一段在 READONLY_SUBDIRS 即视为只读
        ...

manager = WorkspaceManager()
```

```python
# app/api/chat.py  [一起写]（caker）
def _graph_config(session_id: str | None) -> dict:
    sid = (session_id or "demo").strip() or "demo"
    return {"configurable": {"session_id": sid}}   # M10 起再加 thread_id

@router.post("/chat-graph")
async def chat_graph(body: ChatGraphIn) -> ChatGraphOut:
    out = await GRAPH.ainvoke(
        {
            "messages": [],
            "input": body.message,
            "result": "",
            "skip_inject_system": False,
        },
        config=_graph_config(body.session_id),
    )
    return ChatGraphOut(reply=str(out.get("result", "")))
```

```python
# app/tools/read_tool.py 修改  [一起写]
from app.workspace.manager import manager, WorkspaceError

class ReadTool(BaseTool):
    ...
    def _run(self, rel_path, offset=0, limit=200, *, run_manager=None, **kwargs):
        sid = (run_manager.config or {}).get("configurable", {}).get("session_id", "demo")
        try:
            target = manager.resolve(sid, rel_path)
        except WorkspaceError as e:
            return f"<error>{e}</error>"
        # ...剩下读文件逻辑
```

### 验证
```bash
# 越权应被拒
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -d '{"message":"读 ../../../etc/passwd","session_id":"demo"}' \
  -H 'content-type: application/json'
# 期待 reply 中模型说找不到 / 或工具返回 <error>...</error>
```

补一个独立单测：

```python
# tests/test_m7_workspace.py
import pytest
from app.workspace.manager import WorkspaceManager, WorkspaceError

def test_reject_dotdot(tmp_path):
    mgr = WorkspaceManager(str(tmp_path))
    with pytest.raises(WorkspaceError):
        mgr.resolve("demo", "../etc/passwd")

def test_reject_abs(tmp_path):
    mgr = WorkspaceManager(str(tmp_path))
    with pytest.raises(WorkspaceError):
        mgr.resolve("demo", "/etc/passwd")
```

### 易错点
- `Path.resolve()` 会跟随 symlink。如果你给 `skills/` 做了 symlink 指到全局目录，`is_readonly` 不能只看路径前缀，要先 resolve 再比较 prefix。
- `session_id` 不校验就拼路径 = 路径注入。务必白名单字符。

### 对应原报告
§5 工作区隔离；§4 「Bash 需绝对路径」反过来这里我们禁止；§9.4 「workspace 即沙箱」。

---

---

## M8 `call_skill` + SkillsManager

### 目标
- 全局有一个 `skills/` 目录，每个子目录是一个技能（含 `SKILL.md`）。
- 模型可以发 `call_skill(skill_name="hello_skill")`：框架返回 SKILL.md **正文**（剥掉 YAML front matter）作为 `ToolMessage`，**不直接执行**。
- 系统 prompt 里塞「可用 skills 列表」（**只塞元数据，不塞正文**）。

### 前置
M7。

### 文件清单与分工

| 文件 | 分工 |
|------|------|
| `skills/hello_skill/SKILL.md` | `[一起写]` 我给样例，你抄一份属于自己的 |
| `skills/hello_skill/run.py` | `[一起写]` `print("hello, world")` 即可 |
| `app/skills/manager.py` | `[你手敲]` 索引仓库根 `skills/*/SKILL.md`、剥 front matter |
| `app/tools/call_skill_tool.py` | `[你手敲]` Tool 实现 |
| `app/tools/base.py` | `[一起写]` 注册 `CallSkillTool` |
| `system_prompt.md` | `[一起写]` 系统提示词模板（面向使用者；`{skills_meta}` 占位） |
| `app/skills/manager.py` | `[续写]` `load_system_prompt()` / `render_system_prompt()` |
| `app/runtime/nodes.py` | `[一起写]` `inject_system_node` → `render_system_prompt()` |

### 关键代码骨架

```markdown
<!-- skills/hello_skill/SKILL.md  [一起写] -->
---
name: hello_skill
description: A minimal skill that prints hello world.
version: 0.1.0
---

# Operating Instructions

When the user asks you to greet, run:

```
RunPyScript(rel_path="skills/hello_skill/run.py")
```

Then summarize the output to the user.
```

```python
# app/skills/manager.py  [你手敲]
import re
from pathlib import Path

FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

class SkillsManager:
    def __init__(self, root: str | Path | None = None):
        # caker：默认锚到仓库根 skills/，见 app/skills/manager.py
        self.root = Path(root or _REPO_ROOT / "skills").resolve()
        self._index: dict[str, Path] = {}

    def reindex(self) -> None:
        # TODO: 遍历 self.root/<name>/SKILL.md，建立 name -> Path 映射
        ...

    def list_meta(self) -> list[dict]:
        # TODO: 解析每份 SKILL.md 的 front matter (yaml 简单解析或 PyYAML)
        # 返回 [{"name": ..., "description": ..., "version": ...}, ...]
        ...

    def load_body(self, name: str) -> str:
        # TODO:
        # 1. text = Path.read_text()
        # 2. m = FRONT_MATTER_RE.match(text); 若有则剥掉
        # 3. 返回剩余正文
        ...

skills_manager = SkillsManager()
skills_manager.reindex()
```

```python
# app/tools/call_skill_tool.py  [你手敲]
import json
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from app.skills.manager import skills_manager

class CallSkillInput(BaseModel):
    skill_name: str = Field(..., description="Skill name as listed in available skills")

class CallSkillTool(BaseTool):
    name: str = "call_skill"
    description: str = "Load a skill's operating instructions. NOT a runner."
    args_schema: type[BaseModel] = CallSkillInput

    def _run(self, skill_name: str, *, run_manager=None, **_) -> str:
        # TODO:
        # 1. body = skills_manager.load_body(skill_name)  （找不到就返回 error JSON）
        # 2. payload = {
        #      "notice": "This is operating instructions, not user-facing content.",
        #      "skill_name": skill_name,
        #      "instructions": body,
        #    }
        # 3. return json.dumps(payload, ensure_ascii=False)
        ...
```

```python
# app/tools/base.py  [一起写]
def build_default_tools() -> list[BaseTool]:
    return [ReadTool(), CallSkillTool()]

# app/skills/manager.py  [续写]
def load_system_prompt(self) -> str:
    return (_REPO_ROOT / "system_prompt.md").read_text(encoding="utf-8")

def render_system_prompt(self, skills_meta: str | None = None) -> str:
    meta = skills_meta or json.dumps(self.list_meta(), ensure_ascii=False)
    tpl = self.load_system_prompt()
    return tpl.replace("{skills_meta}", meta)

# app/runtime/nodes.py inject_system_node  [一起写]
def inject_system_node(state: GraphState) -> dict:
    if state.get("skip_inject_system", False):
        return {}
    return {"messages": [SystemMessage(content=skills_manager.render_system_prompt())]}
```

**caker**：`reindex()` 遍历 **`skills/<子目录>/SKILL.md`**（`if not child.is_dir(): continue`）。

### 验证
```bash
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -d '{"message":"用 hello_skill 跟我打个招呼"}' \
  -H 'content-type: application/json'
```
预期消息流：模型先 `call_skill("hello_skill")` → 拿到 SKILL.md 正文 → 接着发 `RunPyScript(...)`（M9 才实现）→ 现在还会失败，但能看到「先 call_skill 再尝试运行」的两步行为，验证 M8 OK。

### 易错点
- 别用 `markdown.parse` 之类把 SKILL.md 转 HTML 后塞回；模型要的是**原文**。
- front matter 不剥也能跑，但会浪费 token，且 `name/version` 这类元数据不该混进操作说明。

### 对应原报告
§4 「call_skill 工具：动态加载的核心」、§9.2 「call_skill 即动态加载」。

---

## M9 `RunPyScript`

### 目标
模型可以执行 `skills/<name>/*.py` 子进程，环境注入 `SESSION_ID` / `USER_ID`，回传 `stdout/stderr/exit_code`。

### 前置
M8。

### 文件清单与分工

| 文件 | 分工 |
|------|------|
| `app/workspace/manager.py` | `[一起写]` `session_dir` 内 **symlink** `skills/` → 仓库根 `skills/`（caker 必需） |
| `app/tools/run_py_script_tool.py` | `[你手敲]` 子进程执行、超时、env 注入 |
| `app/tools/base.py` | `[一起写]` 注册 `RunPyScriptTool` |

### 关键代码骨架

```python
# app/tools/run_py_script_tool.py  [你手敲]
import os, json, subprocess, sys
from pathlib import Path
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field
from app.workspace.manager import manager, WorkspaceError

class RunPyInput(BaseModel):
    rel_path: str = Field(..., description="路径必须以 skills/ 开头")
    args: list[str] = Field(default_factory=list)
    timeout_sec: int = 60

class RunPyScriptTool(BaseTool):
    name: str = "RunPyScript"
    description: str = "Run a Python script under skills/. Returns stdout/stderr/exit_code."
    args_schema: type[BaseModel] = RunPyInput

    def _run(self, rel_path, args, timeout_sec, *, run_manager=None, **_):
        # caker：与 ReadTool 相同，用 _session_id_from_run_manager(run_manager)
        # TODO:
        # 1. rel_path 必须以 "skills/" 开头
        # 2. target = manager.resolve(session_id, rel_path)  # 路径相对 WORKSPACE_ROOT/<sid>/
        # 3. cwd=subprocess 用 manager.session_dir(session_id)，勿用仓库根
        # 3. env = {**os.environ, "SESSION_ID": sid, "USER_ID": "..."}（user 留给 M14 改造）
        # 4. proc = subprocess.run([sys.executable, str(target), *args],
        #        capture_output=True, text=True, env=env, timeout=timeout_sec, cwd=workspace)
        # 5. return json.dumps({"exit": proc.returncode,
        #                       "stdout": proc.stdout[-4000:],
        #                       "stderr": proc.stderr[-4000:]})
        ...
```

### 验证
```bash
# 确认会话工作区已有 skills 脚本（symlink 后）
ls -l /tmp/skills/demo/skills/hello_skill/run.py

curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' \
  -d '{"message":"用 hello_skill 打个招呼","session_id":"demo"}'
```
预期：最终 `reply` 包含 `hello, world` 或对它的中文转述。

### 易错点
- `subprocess.run(timeout=...)` 超时抛 `TimeoutExpired` 不会自动 kill 子进程的子进程；如果 skill 启了多进程，得用 `subprocess.Popen + os.killpg`。
- Windows / WSL：子进程 cwd 给 workspace 目录而不是项目根，避免污染。

### 对应原报告
§4 工具分类清单 - 命令执行；§5 「子进程通过 SESSION_ID/USER_ID 环境变量」。

---

## M10 历史持久化（AsyncSqliteSaver）+ `skip_inject_system`

### 目标
- 同一 `session_id` 的多轮对话能延续上下文（LangGraph 检查点写入 `var/state.db`）。
- 有历史时 `skip_inject_system=True`，**跳过** `inject_system`，仍走 `inject_user` 写入本轮 `input`。
- **本地路线**：`AsyncSqliteSaver` 零 PG/S3；**重启 uvicorn 后同 `thread_id` 会话仍在**（SQLite 文件在 `var/`，已 `.gitignore`）。

### 前置
M9。依赖：`langgraph-checkpoint-sqlite`、`aiosqlite`（或 `uv sync`）。

**caker 现状（M8–M9 已落地时）**：`app/runtime/graph.py` **未**接 checkpointer（`GRAPH = build_graph().compile()`），以便 `ainvoke` / `astream_events` 不因同步 `SqliteSaver` 报错。做 M10 时**一次性**接入 `AsyncSqliteSaver` + `route_after_start`，不要只加 checkpointer 不改边。

### 文件清单与分工

| 文件 | 分工 |
|------|------|
| `pyproject.toml` | `[我写]` `langgraph-checkpoint-sqlite`、`aiosqlite` |
| `app/runtime/graph.py` | `[一起写]` `compile(checkpointer=AsyncSqliteSaver)`；`build_graph()` 只 `return g` |
| `app/runtime/nodes.py` `start_node` | `[你手敲]` 看 `state["messages"]` 是否已有内容设 `skip_inject_system` |
| `app/runtime/routes.py` `route_after_start` | `[你手敲]` 新建条件路由 |
| `app/runtime/graph.py` | `[一起写]` `start` 条件边，替换 `start → inject_system` 固定边 |
| `app/api/chat.py` | `[一起写]` `_graph_config` 同时传 `session_id` 与 `thread_id` |

**不做**：`app/state_store/file_backend.py`、手动 `load/save` JSON（原 file 模式留给生产扩展分支）。

### 与 M3–M7 图结构的差异（必读）

M3–M9（**做 M10 之前**，含当前 caker 在 M8–M9 阶段）：

```text
START → start → inject_system → inject_user → llm ⇄ tools → end
              ↑ 固定 add_edge("start", "inject_system")
```

M10 须 **删掉** `g.add_edge("start", "inject_system")`，改为：

```text
START → start ──route_after_start──┬→ inject_system → inject_user ─┐
                                   └→ inject_user（跳过 system）──┘→ llm ⇄ tools → end
```

| 轮次 | `messages`（检查点恢复后） | `route_after_start` | 经过节点 |
|------|---------------------------|---------------------|----------|
| 首轮 | 空 | `inject_system` | start → inject_system → inject_user → … |
| 次轮起 | 含上轮完整对话 | `inject_user` | start → inject_user → …（**不再**注入 SystemMessage） |

`inject_system` → `inject_user` 的边 **保留**；仅 `start` 出口由固定边改为条件边。M6 的 `llm` / `tools` / `end` 边不变。

### `inject_user_node` 与检查点（必读）

- 每轮 API 仍传 `messages: []` 与本轮 `input`（见下 `inputs`）；**不要**在 `ainvoke` 里手工拼接历史。
- **`AsyncSqliteSaver`** 按 `configurable.thread_id` 恢复上一轮结束时的 `messages`（含 System / Human / AI / Tool）。
- `start_node` 仅根据「恢复后 `messages` 是否非空」设置 `skip_inject_system`。
- **`inject_user_node` 逻辑不用改**：仍为 `HumanMessage(content=state["input"])`。`GraphState.messages` 使用 `add_messages` reducer，会把**本轮**用户句 **追加** 到已恢复历史之后。
- 常见误区：在 `start_node` 里把历史 messages 再 `return` 一遍 → 与 reducer 重复追加；或第二轮仍走 `inject_system` → 重复 SystemMessage。

### 关键代码骨架

```python
# pyproject.toml dependencies  [我写]
"langgraph-checkpoint-sqlite>=2.0.0",
"aiosqlite>=0.20",
```

```python
# app/runtime/graph.py  [一起写]（caker + FastAPI 异步）
from pathlib import Path
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

def build_graph():
    g = StateGraph(GraphState)
    # ... 节点同 M6；start 用条件边（见上）...
    return g

Path("var").mkdir(parents=True, exist_ok=True)
# AsyncSqliteSaver.from_conn_string 也是 async context manager；
# 模块级需在 lifespan 或启动钩子里 await __aenter__，或文档化等价写法
GRAPH = ...  # build_graph().compile(checkpointer=checkpointer)
```

**AsyncSqliteSaver 导入（caker 须用异步版）**

| 项 | 值 |
|----|-----|
| pip | `langgraph-checkpoint-sqlite`、`aiosqlite` |
| **正确** | `from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver` |
| **勿用** | 同步 `SqliteSaver` + `await GRAPH.ainvoke` → `does not support async methods` |
| **错误** | `from langgraph_checkpoint_sqlite import ...` → `ModuleNotFoundError` |

自检：`uv run python -c "from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver; print(AsyncSqliteSaver)"`

```python
# app/runtime/nodes.py start_node  [你手敲]
async def start_node(state: GraphState, config) -> dict:
    if state.get("messages") and len(state["messages"]) > 0:
        return {"skip_inject_system": True}
    return {"skip_inject_system": False}
```

```python
# app/runtime/routes.py route_after_start  [你手敲]
def route_after_start(state: GraphState) -> str:
    if state.get("skip_inject_system"):
        return "inject_user"
    return "inject_system"
```

```python
# app/api/chat.py  [一起写]
def _graph_config(session_id: str | None) -> dict:
    sid = (session_id or "demo").strip() or "demo"
    return {"configurable": {"session_id": sid, "thread_id": sid}}

# 每轮 invoke 仍传空 messages，由检查点按 thread_id 恢复历史：
inputs = {
    "messages": [],
    "input": body.message,
    "result": "",
    "skip_inject_system": False,
}
await GRAPH.ainvoke(inputs, config=_graph_config(body.session_id))
```

**与 caker 仓库约定**：聚合字段用 `result`；`end_node` **不必**手动 save——检查点每步自动写入 SQLite。

### 验证
```bash
SID=demo-$(date +%s)
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' \
  -d "{\"message\":\"我叫张三\",\"session_id\":\"$SID\"}"
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -H 'content-type: application/json' \
  -d "{\"message\":\"我叫什么？\",\"session_id\":\"$SID\"}"
```
预期：第二条 `reply` 能答出「张三」。**重启 uvicorn 后**对同一 `$SID` 再发「我叫什么？」仍应能答出（检查点在 `var/state.db`）。

### 易错点
- `thread_id` 给检查点；`session_id` 给 Workspace 工具（M7）——本地可同值，语义分开。
- 只加了 `checkpointer` 却未改 `start` 条件边 → 每轮仍 `inject_system`，与 README「跳过重复 SystemMessage」不一致。
- 未 `mkdir var/` 时 SQLite 可能 `unable to open database file`。
- 同步 `SqliteSaver` 与 `await ainvoke` 不兼容；必须用 **`AsyncSqliteSaver`**。
- `from_conn_string` 是 context manager，不能直接把 manager 对象传给 `compile()`。
- 忘记 `compile(checkpointer=...)` 时，第二轮 `messages` 仍为空。
- `add_messages` 是追加：每轮只传本轮 `input`，勿在 `ainvoke` 里重复塞全量历史。

### 对应原报告
§3 节点 1 start；§7 StateStore（本地用 LangGraph SQLite checkpoint，不对标 S3/PG 全量实现）。

---

## M11 `result_set` + `apply_result_set`

### 目标
- 多一个 `result_set(text="...")` 工具，模型用它**正式产出最终回答**。
- `apply_result_set` 节点把工具结果里的 `text` 取出写入 **`state["result"]`**（caker 不用 `result_text`），并 `result_set_handled=True`，路由直奔 `end`。
- 流式请求时**不暴露**该工具（流式靠 token 流回结果，不需要 `result_set`）。

### 前置
M10。

### 文件清单与分工

| 文件 | 分工 |
|------|------|
| `app/tools/result_set_tool.py` | `[你手敲]` |
| `app/runtime/nodes.py` `apply_result_set_node` | `[你手敲]` |
| `app/runtime/routes.py` `route_after_tools` | `[你手敲]` |
| `app/runtime/llm.py` `_get_tools_for_state` | `[一起写]` 流式不绑 result_set |
| `app/runtime/graph.py` | `[一起写]` 加节点和条件边 |

### 关键代码骨架

```python
# app/tools/result_set_tool.py  [你手敲]
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

class ResultSetInput(BaseModel):
    text: str = Field(..., description="The final answer for the user")

class ResultSetTool(BaseTool):
    name: str = "result_set"
    description: str = "Submit your final answer to the user. Call this last."
    args_schema: type[BaseModel] = ResultSetInput

    def _run(self, text: str, *, run_manager=None, **_) -> str:
        return text   # ToolMessage.content 就是 text，便于 apply_result_set 读
```

```python
# app/runtime/nodes.py  [你手敲]
from langchain_core.messages import ToolMessage

def apply_result_set_node(state, config):
    last = state["messages"][-1]
    # TODO:
    # 1. 仅当 last 是 ToolMessage 且 last.name == "result_set"
    # 2. 写 result = last.content（caker 字段名 result）
    # 3. result_set_handled = True
    ...
```

```python
# app/runtime/routes.py  [你手敲]
def route_after_tools(state) -> str:
    # TODO:
    # 1. 若 state.get("result_set_handled") -> "end"
    # 2. 否则 -> "llm" 继续循环（summary 节点放到 M14）
    ...
```

```python
# app/runtime/state.py 增量
class GraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    result: str                    # caker
    result_set_handled: bool
    skip_inject_system: bool
    streaming: bool
```

```python
# app/runtime/llm.py  [一起写]
def _get_tools_for_state(streaming: bool):
    tools = [ReadTool(), CallSkillTool(), RunPyScriptTool()]
    if not streaming:
        tools.append(ResultSetTool())
    return tools
```

### 验证
```bash
curl -s -X POST :8000/api/v2/chat-graph \
  -d '{"message":"读 data/a.txt 然后用 result_set 给我最终答案"}' \
  -H 'content-type: application/json'
```
预期：
- `messages` 里能看到 `ToolMessage(name=result_set, content="...最终答案...")`；
- `reply` 即该最终答案；
- 状态里 `result_set_handled=True`。

### 易错点
- 别让 `apply_result_set` **添加新消息**，它只改 `result` 和标志位；否则下一轮历史会有奇怪空 AIMessage。
- 流式（M4）路径上**不绑** `result_set`，否则模型会优先调它而不是流式吐字。

### 对应原报告
§3 节点 6 `apply_result_set`、节点 8 end；§3 路由表 `_route_after_tools`。

---

---

## M14 `summary` 节点（长上下文压缩）

### 目标
当 `len(messages)` token 超阈值时，先压缩历史，再继续 LLM 调用。

### 前置
M11（图里要有完整循环）。

### 文件清单与分工

| 文件 | 分工 |
|------|------|
| `app/summary/handler.py` | `[一起写]` token 估算 + summarize prompt |
| `app/runtime/nodes.py` `summary_node` | `[你手敲]` |
| `app/runtime/routes.py` `route_after_tools` | `[你手敲]` 增加超阈值分支 |
| `app/runtime/graph.py` | `[一起写]` 加节点和边 |

### 关键代码骨架

```python
# app/summary/handler.py  [一起写]
import tiktoken
from langchain_core.messages import (
    BaseMessage, RemoveMessage, SystemMessage, HumanMessage, AIMessage,
)
from app.runtime.llm import get_llm

ENCODING = tiktoken.get_encoding("cl100k_base")
MAX_INPUT_TOKENS = 8000           # 视模型而定
SUMMARY_COND_RATIO = 0.6          # 超过 60% 就触发
SUMMARY_PROMPT = (
    "请把下面对话压缩成保留事实/结论/未完成动作的中文摘要，控制在 400 字内：\n\n{dialog}"
)

def estimate_tokens(messages: list[BaseMessage]) -> int:
    return sum(len(ENCODING.encode(m.content or "")) for m in messages)

def need_summary(messages) -> bool:
    return estimate_tokens(messages) >= MAX_INPUT_TOKENS * SUMMARY_COND_RATIO

def summarize(messages) -> SystemMessage:
    dialog = "\n".join(f"[{m.type}] {m.content}" for m in messages)
    out = get_llm().invoke([HumanMessage(content=SUMMARY_PROMPT.format(dialog=dialog))])
    return SystemMessage(content=f"[SUMMARY]\n{out.content}")
```

```python
# app/runtime/nodes.py  [你手敲]
from langgraph.graph.message import RemoveMessage, REMOVE_ALL_MESSAGES
from app.summary.handler import summarize

async def summary_node(state, config):
    summary_msg = summarize(state["messages"])
    # TODO:
    # 1. 删除全部老消息：messages 里追加 RemoveMessage(REMOVE_ALL_MESSAGES)
    # 2. 重置为 [summary_msg, 最后一条用户输入]
    ...
```

```python
# app/runtime/routes.py  [你手敲]
from app.summary.handler import need_summary

def route_after_tools(state) -> str:
    if state.get("result_set_handled"):
        return "end"
    if need_summary(state["messages"]):
        return "summary"
    return "llm"
```

### 验证

构造一个会触发的测试：

```python
# tests/test_m14_summary.py
import pytest
from langchain_core.messages import HumanMessage, AIMessage
from app.summary.handler import need_summary

def test_need_summary_true():
    msgs = [HumanMessage(content="x"*40000)]
    assert need_summary(msgs) is True
```

实跑：用一段超长 user input 启动一次 `chat-graph`，看日志：是否走到 `summary` 节点；之后 `messages` 应只剩 2 条。

### 易错点
- `RemoveMessage(REMOVE_ALL_MESSAGES)` 必须在**同一节点的 return** 里和新消息一起返回，否则会把新加的也删了。
- 摘要会丢工具中间结果——只保留 user/AI 文本的摘要；如需保留 tool 关键产物，得自己抽。

### 对应原报告
§3 节点 7 summary；§3 路由表 token 超阈值分支。

---

## M15 MemPalace 雏形（ChromaDB）

### 目标
- 跨会话语义记忆：每次对话结束把摘要存入 ChromaDB；新会话开始时根据当前 user 输入做向量召回，作为 `mempalace_inject` 的引导消息。
- L0 结构化记忆暂用本地 JSON 文件代替（生产里是更复杂的存储）。

### 前置
M14（要有摘要能力）；`chromadb` 已装。

### 文件清单与分工

| 文件 | 分工 |
|------|------|
| `app/mempalace/chroma_store.py` | `[一起写]` 简化版 collection 封装 |
| `app/mempalace/injector.py` | `[你手敲]` `should_inject_mempalace_bootstrap` + 召回 + 拼装 HumanMessage(JSON) |
| `app/runtime/nodes.py` `mempalace_inject_node` | `[你手敲]` |
| `app/runtime/graph.py` | `[一起写]` 把 `mempalace_inject` 接到 `start/inject_system → llm` 之间 |

### 关键代码骨架

```python
# app/mempalace/chroma_store.py  [一起写]
import chromadb
from chromadb.config import Settings as ChromaSettings
from app.config import settings

_client = chromadb.PersistentClient(path=settings.workspace_root + "/../chroma",
                                    settings=ChromaSettings(anonymized_telemetry=False))
_coll = _client.get_or_create_collection("mempalace")

def add(memory_id: str, text: str, metadata: dict):
    _coll.upsert(ids=[memory_id], documents=[text], metadatas=[metadata])

def search(query: str, k: int = 3, where: dict | None = None):
    res = _coll.query(query_texts=[query], n_results=k, where=where)
    return list(zip(res["ids"][0], res["documents"][0], res["metadatas"][0]))
```

```python
# app/mempalace/injector.py  [你手敲]
import json
from langchain_core.messages import HumanMessage
from app.mempalace import chroma_store

WAKEUP = "下面是来自长期记忆的相关信息，仅供参考。"

def should_inject(messages) -> bool:
    # TODO:
    # 1. 若上一条是 HumanMessage 且本轮还未注入过 mempalace -> True
    # 2. 否则 -> False（避免反复灌）
    ...

def build_bootstrap(user_text: str, user_id: str) -> HumanMessage | None:
    hits = chroma_store.search(user_text, k=3, where={"user_id": user_id})
    if not hits:
        return None
    # TODO: 把 hits 包成 JSON：{wakeup, recall:[{id,text,score}]}
    ...
```

```python
# app/runtime/nodes.py mempalace_inject_node  [你手敲]
from app.mempalace.injector import should_inject, build_bootstrap

async def mempalace_inject_node(state, config):
    if not should_inject(state["messages"]):
        return {}
    user_msg = next(m for m in reversed(state["messages"]) if m.type == "human")
    boot = build_bootstrap(user_msg.content, config["configurable"].get("user_id", "anon"))
    if boot is None:
        return {}
    return {"messages": [boot]}
```

```python
# end_node 增量：把本轮摘要塞进 mempalace
from app.summary.handler import summarize
from app.mempalace import chroma_store
import uuid

async def end_node(state, config):
    sid = config["configurable"]["session_id"]
    user_id = config["configurable"].get("user_id", "anon")
    last_ai = state["messages"][-1]
    state_store.save(sid, state["messages"])
    sm = summarize(state["messages"]).content
    chroma_store.add(uuid.uuid4().hex, sm, {"session_id": sid, "user_id": user_id})
    return {"result": last_ai.content}   # caker
```

### 验证
```bash
USER=u-demo
SID1=mp1-$(date +%s)
SID2=mp2-$(date +%s)

# 第一次会话：透露关键信息
curl -s -X POST :8000/api/v2/chat-graph \
  -d "{\"message\":\"我家猫叫小酥，灰色的。\",\"session_id\":\"$SID1\"}" \
  -H "x-user-id: $USER" -H 'content-type: application/json'

# 第二次会话（不同 session_id，相同 user_id）：靠召回
curl -s -X POST :8000/api/v2/chat-graph \
  -d "{\"message\":\"我家猫是什么颜色的？\",\"session_id\":\"$SID2\"}" \
  -H "x-user-id: $USER" -H 'content-type: application/json'
```
预期：第二次能答出灰色（前提是路由把 `user_id` 注入了 `configurable`）。

### 易错点
- ChromaDB 默认会下载 `all-MiniLM-L6-v2` 模型；离线机器要预先 `EMBEDDING_FUNCTION` 走 OpenAI embedding。
- 召回是「软上下文」，模型可能不采信。可以在 `WAKEUP` 里强调「优先核对该信息再回答」。
- L0 结构化记忆如果在练手项目里需要，简单做：`app/mempalace/l0.py` 用 `<workspace>/.l0.json` 存 key-value 即可。

### 对应原报告
§3 节点 3 mempalace_inject；§9.5 「MemPalace 即长期记忆」。

---

## 附录 A：依赖清单（pyproject.toml 节选）

```toml
[project]
name = "mini-agent-skills"
version = "0.0.1"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "pydantic>=2.7",
  "pydantic-settings>=2.4",
  "langgraph>=0.2.50",
  "langchain-core>=0.3",
  "langchain-openai>=0.2",
  "asyncpg>=0.29",
  "tiktoken>=0.7",
  "chromadb>=0.5",
  "boto3>=1.34",
]

[tool.uv]
dev-dependencies = ["pytest>=8", "httpx>=0.27"]
```

## 附录 B：里程碑总览（贴桌面）

| M | 你能跑 | 报告对照 |
|---|--------|----------|
| M0 | `/health` | §2 第一层 |
| M1 | echo 路由 | §2 第一层 |
| M2 | LLM 一发一收 | §3 节点 4 |
| M3 | 图 start→llm→end | §3 §9.1 |
| M4 | SSE 流式 | §3 节点 4 / §6 前置 |
| M5 | Read 工具 | §4 / §5 |
| M6 | tool_calls 循环 | §3 节点 5 / 路由 |
| M7 | Workspace 沙箱 | §5 / §9.4 |
| M8 | call_skill 加载说明 | §4 / §9.2 |
| M9 | RunPyScript 子进程 | §4 / §5 |
| M10 | 多轮历史（AsyncSqliteSaver / `var/state.db`） | §3 节点 1 / §7（子集） |
| M11 | result_set 终态 | §3 节点 6,8 |
| M14 | summary 压缩 | §3 节点 7 |
| M15 | MemPalace 召回 | §3 节点 3 / §9.5 |

> 原报告 **§6 Pipeline / 游标恢复** 不在本地路线跟写；需要分布式能力时另开分支扩展。

## 附录 C：调试技巧

- `LANGCHAIN_TRACING_V2=true` + LangSmith 看每个节点的 input/output。
- 不想接 LangSmith 时，给每个节点开头加 `print(f"[{node}] msgs={len(state['messages'])}")` 是最朴素也最有效的。
- LangGraph 的 `graph.get_graph().print_ascii()` 能把图结构画到终端。
- 多轮历史：确认 `configurable.thread_id` 与第二轮 `skip_inject_system` 是否生效（`print` `start_node` 的 `len(messages)`）。

## 附录 D：和原报告的映射读法

每个 M 末尾的「对应原报告」指向报告里 §X 小节。建议每攻下一个 M，回去把对应章节再扫一遍——这时你**实际写过代码**，再读会发现报告里很多细节（如 `_llm_with_result_set` 这种命名）都能落地为你刚敲过的那个分支。



