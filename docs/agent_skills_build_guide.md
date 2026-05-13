# Agent Skills 跟写指南（Build-along）

> 配合阅读：[原深度研究报告](/mnt/c/Users/PF-4BA9TH/Desktop/user_attachments_session_a29c06ca28284858b68f5de84ede3306_outputs_agent_skills_deep_research_report.md)
> 用法：每个里程碑 M# 都能跑出来一个比上一个强一点点的 demo；不绿就别往下走。

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
| 关系库 | PostgreSQL 14+ | Pipeline chunk 表、checkpoint |
| 对象存储 | S3 / MinIO | StateStore file 模式 |
| 向量库 | ChromaDB | MemPalace 语义记忆 |
| 子进程脚本 | Python 3.11 + Node.js 20 | `RunPyScript`、`RunJsTsScript` |

环境变量（贯穿全程）：

```bash
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1   # 或自家网关
OPENAI_MODEL=gpt-4o-mini
WORKSPACE_ROOT=/tmp/skills
PG_DSN=postgres://user:pass@localhost:5432/agent_skills
S3_ENDPOINT=http://localhost:9000
S3_BUCKET=agent-skills-state
CHROMA_PATH=./var/chroma
```

---

## 2. 项目骨架（M0 之前先建好）

```
mini_skills/
├── pyproject.toml
├── .env.example
├── docker-compose.yaml         # PG + MinIO + Chroma
├── README.md
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # pydantic-settings
│   ├── api/
│   │   ├── __init__.py
│   │   └── chat.py             # POST /api/v2/stream 等
│   ├── runtime/
│   │   ├── __init__.py
│   │   ├── graph.py            # LangGraph StateGraph
│   │   ├── nodes.py            # 节点函数
│   │   ├── routes.py           # 路由函数
│   │   └── state.py            # State TypedDict
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py             # 基类、注册表
│   │   ├── read_tool.py
│   │   ├── write_tool.py
│   │   ├── edit_tool.py
│   │   ├── bash_tool.py
│   │   ├── call_skill_tool.py
│   │   └── run_py_script_tool.py
│   ├── workspace/
│   │   ├── __init__.py
│   │   └── manager.py          # resolve_workspace_path 等
│   ├── skills/
│   │   ├── __init__.py
│   │   └── manager.py          # SKILL.md 索引/加载
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── service.py          # 生产/消费/PG 写入
│   │   └── schema.sql
│   ├── state_store/
│   │   ├── __init__.py
│   │   ├── file_backend.py
│   │   └── pg_backend.py
│   ├── summary/
│   │   └── handler.py
│   └── mempalace/
│       ├── __init__.py
│       ├── chroma_store.py
│       └── injector.py
├── skills/                     # SKILL.md 包
│   └── hello_skill/
│       ├── SKILL.md
│       └── run.py
└── tests/
    ├── test_m1_echo.py
    ├── test_m3_graph.py
    ...
```

> 这个骨架你**不必一次建完**。每个 M 只新增它需要的目录/文件。

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
# app/config.py  [我写]
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = Field("", alias="OPENAI_API_KEY")
    openai_base_url: str = Field("https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_model: str = Field("gpt-4o-mini", alias="OPENAI_MODEL")
    workspace_root: str = Field("/tmp/skills", alias="WORKSPACE_ROOT")
    pg_dsn: str = Field("", alias="PG_DSN")

settings = Settings()
```

```python
# app/main.py  [一起写]
from fastapi import FastAPI

app = FastAPI(title="mini-agent-skills")

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
M1，且 `OPENAI_API_KEY` 可用。

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
        model=model or settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.2,
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
    result_text: str
    skip_inject_system: bool   # 留给 M10 用，先恒为 False
```

```python
# app/runtime/nodes.py  [你手敲] —— 这是核心练习，自己实现
from app.runtime.llm import get_llm
from langchain_core.messages import SystemMessage

# TODO: async def start_node(state, config): 直接 return {} （历史加载留 M10）

# TODO: def inject_system_node(state, config):
#   注入 SystemMessage("You are a helpful Agent. ...")

# TODO: def llm_node(state, config):
#   ai = get_llm().invoke(state["messages"])
#   return {"messages": [ai]}

# TODO: async def end_node(state, config):
#   把最后一条 AIMessage 的 content 写入 result_text
```

```python
# app/runtime/graph.py  [你手敲]
from langgraph.graph import StateGraph, START, END
from app.runtime.state import GraphState
from app.runtime import nodes

def build_graph():
    g = StateGraph(GraphState)
    g.add_node("start", nodes.start_node)
    g.add_node("inject_system", nodes.inject_system_node)
    g.add_node("llm", nodes.llm_node)
    g.add_node("end", nodes.end_node)
    g.add_edge(START, "start")
    g.add_edge("start", "inject_system")
    g.add_edge("inject_system", "llm")
    g.add_edge("llm", "end")
    g.add_edge("end", END)
    return g.compile()

GRAPH = build_graph()
```

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
        inputs = {"messages": [HumanMessage(content=body.message)],
                  "result_text": "", "skip_inject_system": False}
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
§3 节点 4 流式区分；§6 PipelineService 的“前置内功”——本 M 只做单连接 SSE，PipelineService 的解耦留到 M12。

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
# app/runtime/nodes.py 改 llm_node  [一起写]
from app.tools.read_tool import ReadTool
from app.runtime.llm import get_llm_with_tools

_TOOLS = [ReadTool()]

def llm_node(state, config):
    llm = get_llm_with_tools(_TOOLS)
    ai = llm.invoke(state["messages"])
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
| `app/runtime/nodes.py` | `[一起写]` `tools_node = ToolNode(_TOOLS)` |

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
    g.add_node("tools", ToolNode(nodes._TOOLS))
    g.add_node("end", nodes.end_node)

    g.add_edge(START, "start")
    g.add_edge("start", "inject_system")
    g.add_edge("inject_system", "llm")
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
        # 5. （可选）symlink skills/、books/ 到全局只读包
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
# app/api/chat.py  [一起写]
from langgraph.types import Configurable

@router.post("/chat-graph")
async def chat_graph(body: EchoIn):
    sid = body.session_id or "demo"
    cfg = {"configurable": {"session_id": sid}}
    state = await GRAPH.ainvoke(
        {"messages": [HumanMessage(content=body.message)],
         "result_text": "", "skip_inject_system": False},
        config=cfg,
    )
    return {"reply": state["result_text"]}
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
| `app/skills/manager.py` | `[你手敲]` 索引、读取、剥 front matter |
| `app/tools/call_skill_tool.py` | `[你手敲]` Tool 实现 |
| `app/runtime/nodes.py` | `[一起写]` `inject_system_node` 注入技能列表 JSON |

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
    def __init__(self, root: str = "skills"):
        self.root = Path(root).resolve()
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
# app/runtime/nodes.py inject_system_node  [一起写] 增量
import json
from langchain_core.messages import SystemMessage
from app.skills.manager import skills_manager

def inject_system_node(state, config):
    if state.get("skip_inject_system"):
        return {}
    skills_meta = json.dumps(skills_manager.list_meta(), ensure_ascii=False)
    sys = SystemMessage(content=(
        "You are a helpful Agent.\n"
        "When you need a skill, call the `call_skill` tool by name to load its instructions, "
        "then follow them step-by-step using other tools.\n"
        f"Available skills: {skills_meta}"
    ))
    return {"messages": [sys]}
```

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
| `app/tools/run_py_script_tool.py` | `[你手敲]` 子进程执行、超时、env 注入 |
| `app/runtime/nodes.py` | `[一起写]` 把工具加进 `_TOOLS` |

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
        sid = (run_manager.config or {}).get("configurable", {}).get("session_id", "demo")
        # TODO:
        # 1. 如果 rel_path 不是以 "skills/" 开头 -> 拒绝
        # 2. target = manager.resolve(sid, rel_path) 并保证存在 .py
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
curl -s -X POST http://127.0.0.1:8000/api/v2/chat-graph \
  -d '{"message":"用 hello_skill 打个招呼"}' \
  -H 'content-type: application/json'
```
预期：最终 `reply` 包含 `hello, world` 或对它的中文转述。

### 易错点
- `subprocess.run(timeout=...)` 超时抛 `TimeoutExpired` 不会自动 kill 子进程的子进程；如果 skill 启了多进程，得用 `subprocess.Popen + os.killpg`。
- Windows / WSL：子进程 cwd 给 workspace 目录而不是项目根，避免污染。

### 对应原报告
§4 工具分类清单 - 命令执行；§5 「子进程通过 SESSION_ID/USER_ID 环境变量」。

---

## M10 历史持久化（file 模式）+ `skip_inject_system`

### 目标
- 第二轮请求自动加载第一轮的对话历史。
- 有历史时 `start_node` 设 `skip_inject_system=True`，路由跳过 `inject_system`。

### 前置
M9。

### 文件清单与分工

| 文件 | 分工 |
|------|------|
| `app/state_store/file_backend.py` | `[一起写]` 序列化/反序列化 messages（HumanMessage/AIMessage/SystemMessage/ToolMessage）|
| `app/runtime/nodes.py` `start_node` `end_node` | `[你手敲]` |
| `app/runtime/routes.py` `route_after_start` | `[你手敲]` |
| `app/runtime/graph.py` | `[一起写]` 接条件边 |

### 关键代码骨架

```python
# app/state_store/file_backend.py  [一起写]
import json
from pathlib import Path
from langchain_core.messages import (
    AIMessage, HumanMessage, SystemMessage, ToolMessage, BaseMessage,
)

CLS_MAP = {"human": HumanMessage, "ai": AIMessage,
           "system": SystemMessage, "tool": ToolMessage}

def msg_to_dict(m: BaseMessage) -> dict:
    return {
        "type": m.type,
        "content": m.content,
        "tool_calls": getattr(m, "tool_calls", None),
        "tool_call_id": getattr(m, "tool_call_id", None),
        "name": getattr(m, "name", None),
    }

def dict_to_msg(d: dict) -> BaseMessage:
    cls = CLS_MAP[d["type"]]
    kwargs = {"content": d["content"]}
    if d["type"] == "ai" and d.get("tool_calls"):
        kwargs["tool_calls"] = d["tool_calls"]
    if d["type"] == "tool":
        kwargs["tool_call_id"] = d["tool_call_id"]
        kwargs["name"] = d.get("name", "")
    return cls(**kwargs)

class FileStateStore:
    def __init__(self, root: str = "./var/state"):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, sid: str) -> Path:
        return self.root / sid / "latest.json"

    def load(self, sid: str) -> list[BaseMessage]:
        p = self._path(sid)
        if not p.exists(): return []
        data = json.loads(p.read_text("utf-8"))
        return [dict_to_msg(d) for d in data.get("messages", [])]

    def save(self, sid: str, messages: list[BaseMessage]) -> None:
        p = self._path(sid); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(
            {"messages": [msg_to_dict(m) for m in messages]},
            ensure_ascii=False), "utf-8")

state_store = FileStateStore()
```

```python
# app/runtime/nodes.py 增量  [你手敲]
from app.state_store.file_backend import state_store

async def start_node(state, config):
    sid = config["configurable"]["session_id"]
    history = state_store.load(sid)
    # TODO:
    # 1. 当前 user 输入应该已经在 state["messages"][-1]
    # 2. 若 history 非空 -> 返回 {
    #       "messages": history + [state["messages"][-1]],
    #       "skip_inject_system": True,
    #    }
    # 3. 否则 -> 返回 {"skip_inject_system": False}
    ...

async def end_node(state, config):
    sid = config["configurable"]["session_id"]
    last_ai = state["messages"][-1]
    state_store.save(sid, state["messages"])
    return {"result_text": last_ai.content if hasattr(last_ai, "content") else ""}
```

```python
# app/runtime/routes.py  [你手敲]
def route_after_start(state) -> str:
    return "mempalace_inject" if state.get("skip_inject_system") else "inject_system"
```

```python
# app/runtime/graph.py 改造  [一起写]
g.add_conditional_edges("start", route_after_start,
                        {"inject_system": "inject_system",
                         "mempalace_inject": "llm"})  # M15 前先直连 llm
```

### 验证
```bash
SID=demo-$(date +%s)
curl -s -X POST :8000/api/v2/chat-graph \
  -d "{\"message\":\"我叫张三\",\"session_id\":\"$SID\"}" -H 'content-type: application/json'
curl -s -X POST :8000/api/v2/chat-graph \
  -d "{\"message\":\"我叫什么？\",\"session_id\":\"$SID\"}" -H 'content-type: application/json'
```
预期：第二条能答出「张三」。

观察 `./var/state/<SID>/latest.json`，确认 messages 被序列化。

### 易错点
- `LangGraph` 的 `add_messages` reducer 是**追加**，不能在 `start_node` 里 `return {"messages": history}` 期望覆盖；要 `return {"messages": history + [user_msg]}`，并且**初始 invoke 时也只传当前 user 一条**。
- `ToolMessage` 必须带 `tool_call_id`，不然反序列化重放时 LLM 会拒绝。

### 对应原报告
§3 节点 1 start；§7 StateStore（先做 file 模式，PG 在 M12 一起做）。

---

## M11 `result_set` + `apply_result_set`

### 目标
- 多一个 `result_set(text="...")` 工具，模型用它**正式产出最终回答**。
- `apply_result_set` 节点把工具结果里的 `text` 取出写入 `state.result_text`，并 `result_set_handled=True`，路由直奔 `end`。
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
    # 2. 写 result_text = last.content
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
    result_text: str
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
- 别让 `apply_result_set` **添加新消息**，它只改 `result_text` 和标志位；否则下一轮历史会有奇怪空 AIMessage。
- 流式（M4）路径上**不绑** `result_set`，否则模型会优先调它而不是流式吐字。

### 对应原报告
§3 节点 6 `apply_result_set`、节点 8 end；§3 路由表 `_route_after_tools`。

---

---

## M12 PipelineService：生产者-消费者解耦

### 目标
- LLM 执行**不依赖** SSE 连接：`POST /api/v2/stream` 内部把图执行投到后台 task。
- 每条 SSE 行同时**写入 PG `web_chat_pipeline_chunk`** + **广播到 asyncio.Queue**。
- 客户端断开重连可从游标继续（M13 做完整恢复，M12 先把生产端跑起来）。

### 前置
M11；`PG_DSN` 可用；`asyncpg` 已装。

### 文件清单与分工

| 文件 | 分工 |
|------|------|
| `app/pipeline/schema.sql` | `[我写]` 建表 + 唯一约束 |
| `app/pipeline/service.py` | `[一起写]` 我给类骨架（连接池、生产、广播、PG 写入），你填 `_produce` 主循环和入队语义 |
| `app/api/chat.py` `/stream` | `[一起写]` 改为「投后台任务 + 同连接消费」 |
| `app/main.py` | `[一起写]` 启动时 init pg pool / 建表 |

### 关键代码骨架

```sql
-- app/pipeline/schema.sql  [我写]
CREATE TABLE IF NOT EXISTS web_chat_pipeline_chunk (
    session_id  TEXT NOT NULL,
    seq         BIGINT NOT NULL,
    turn_id     TEXT NOT NULL,
    event_id    TEXT NOT NULL,
    line        TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (session_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_chunk_turn ON web_chat_pipeline_chunk(session_id, turn_id);
```

```python
# app/pipeline/service.py  [一起写]
import asyncio, json, uuid
import asyncpg
from collections import defaultdict
from typing import AsyncIterator
from app.runtime.graph import GRAPH
from app.runtime.sse import sse_pack
from langchain_core.messages import HumanMessage

class PipelineService:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._producers: dict[str, asyncio.Task] = {}

    async def init(self):
        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=8)

    async def _persist(self, sid: str, seq: int, turn_id: str, event_id: str, line: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO web_chat_pipeline_chunk(session_id,seq,turn_id,event_id,line)"
                " VALUES($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING",
                sid, seq, turn_id, event_id, line,
            )

    def _broadcast(self, sid: str, payload: bytes):
        for q in self._subs[sid]:
            q.put_nowait(payload)

    async def _produce(self, sid: str, message: str):
        turn_id = uuid.uuid4().hex
        seq = await self._next_seq(sid)
        # TODO: 用 GRAPH.astream_events(...) 拿 LLM token 流
        # 每个 token / 每个工具事件包成一行 SSE：
        #   line = sse_pack("delta", {"text": token}).decode()
        #   await self._persist(sid, seq, turn_id, event_id=uuid.uuid4().hex, line=line)
        #   self._broadcast(sid, line.encode())
        #   seq += 1
        # 结束时 broadcast event=done
        ...

    async def _next_seq(self, sid: str) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COALESCE(MAX(seq), 0) AS s FROM web_chat_pipeline_chunk WHERE session_id=$1",
                sid)
            return row["s"] + 1

    def schedule_turn(self, sid: str, message: str) -> None:
        # 已在跑就不重复投递
        if sid in self._producers and not self._producers[sid].done():
            return
        self._producers[sid] = asyncio.create_task(self._produce(sid, message))

    async def subscribe(self, sid: str) -> AsyncIterator[bytes]:
        q: asyncio.Queue = asyncio.Queue()
        self._subs[sid].append(q)
        try:
            while True:
                # TODO: 自动结束：若 producer 已 done 且队列空 -> break
                payload = await q.get()
                yield payload
        finally:
            self._subs[sid].remove(q)

pipeline = PipelineService(dsn=settings.pg_dsn)
```

```python
# app/api/chat.py /stream 改造  [一起写]
@router.post("/stream")
async def stream_v2(body: EchoIn):
    sid = body.session_id or "demo"
    pipeline.schedule_turn(sid, body.message)
    async def gen():
        async for line in pipeline.subscribe(sid):
            yield line
    return StreamingResponse(gen(), media_type="text/event-stream")
```

### 验证
```bash
SID=p-$(date +%s)

# 终端 A：消费
curl -N -X POST :8000/api/v2/stream \
  -d "{\"message\":\"数到 10\",\"session_id\":\"$SID\"}" \
  -H 'content-type: application/json'

# 终端 B：在 A 跑到一半时 Ctrl+C，再起一条相同 SID 的请求（M13 才能续读，但应能看到生产仍在）
psql $PG_DSN -c "SELECT seq, event_id FROM web_chat_pipeline_chunk WHERE session_id='$SID' ORDER BY seq;"
```
预期：A 流式完成；PG 表里有 N 条 chunk；即使 A 断开，PG 继续增长直到 producer 完成。

### 易错点
- `asyncio.create_task` 没人持有 reference 时可能被 GC 掉；必须存进 `self._producers`。
- 多 worker（uvicorn `--workers 4`）下 `_subs` / `_producers` 是**进程内**的；要支持跨进程订阅得用 PG `LISTEN/NOTIFY` 或 Redis pubsub —— 本指南先单进程。
- `seq` 用 `MAX(seq)+1` 在并发下会有竞争。生产中改成 `INSERT ... RETURNING seq` 配 `BIGSERIAL` 或者 PG 序列（建议改：本练习里足够）。

### 对应原报告
§6 PipelineService 全节；§9.3 「Pipeline 即持久化日志」。

---

## M13 游标恢复

### 目标
新增 `POST /api/v1/sessions/{sid}/pipeline`：客户端带 `after_seq` / `after_event_id` / `after_turn_id` 续读历史 chunk + 后续实时 chunk。

### 前置
M12。

### 文件清单与分工

| 文件 | 分工 |
|------|------|
| `app/api/chat.py` | `[你手敲]` 新路由，参数解析 |
| `app/pipeline/service.py` | `[一起写]` `replay(sid, cursor)` + 拼接实时订阅 |

### 关键代码骨架

```python
# app/pipeline/service.py 增量  [一起写]
async def replay(self, sid: str, after_seq: int | None = None,
                 after_event_id: str | None = None,
                 after_turn_id: str | None = None) -> AsyncIterator[bytes]:
    # 1) 先吐历史
    where, args = "session_id=$1", [sid]
    if after_seq is not None:
        where += f" AND seq>${len(args)+1}"; args.append(after_seq)
    elif after_event_id:
        where += (f" AND seq > (SELECT seq FROM web_chat_pipeline_chunk "
                  f"WHERE session_id=$1 AND event_id=${len(args)+1})")
        args.append(after_event_id)
    elif after_turn_id:
        where += (f" AND seq > (SELECT MAX(seq) FROM web_chat_pipeline_chunk "
                  f"WHERE session_id=$1 AND turn_id=${len(args)+1})")
        args.append(after_turn_id)

    async with self.pool.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT seq,line FROM web_chat_pipeline_chunk WHERE {where} ORDER BY seq", *args)
    last_seq = after_seq or 0
    for r in rows:
        last_seq = r["seq"]; yield r["line"].encode()

    # 2) 接实时（避免漏掉 replay 与 subscribe 之间生成的）
    async for payload in self.subscribe(sid):
        yield payload
```

```python
# app/api/chat.py  [你手敲]
@router.post("/api/v1/sessions/{sid}/pipeline")
async def pipeline_consume(sid: str,
                           after_seq: int | None = None,
                           after_event_id: str | None = None,
                           after_turn_id: str | None = None):
    async def gen():
        async for line in pipeline.replay(sid, after_seq, after_event_id, after_turn_id):
            yield line
    return StreamingResponse(gen(), media_type="text/event-stream")
```

### 验证
```bash
SID=r-$(date +%s)

# 1) 投一次任务
curl -N -X POST :8000/api/v2/stream \
  -d "{\"message\":\"列出 10 个城市\",\"session_id\":\"$SID\"}" \
  -H 'content-type: application/json' &

# 2) 主动断开（kill 上面），然后续读
LAST_SEQ=$(psql -tA $PG_DSN -c \
  "SELECT MAX(seq) FROM web_chat_pipeline_chunk WHERE session_id='$SID';")
curl -N "http://127.0.0.1:8000/api/v1/sessions/$SID/pipeline?after_seq=$LAST_SEQ"
```
预期：续读拿到 `after_seq` 之后的所有 chunk + 当前未发送的实时 chunk，输出与不断开一致。

### 易错点
- **重复或丢消息**：在 `replay` → `subscribe` 切换的瞬间，新 chunk 可能既写了 PG 又被 broadcast。最简单的去重：在订阅期内记录已 yield 的最大 seq，subscribe 来的旧 seq 跳过。
- 三种游标**不要同时传**，让前端只用一种；服务端写好优先级（seq > event_id > turn_id）。

### 对应原报告
§6 「游标恢复」+「自动结束」；§8 阶段 D。

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
    return {"result_text": last_ai.content}
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
| M10 | 历史持久化 | §3 节点 1 / §7 |
| M11 | result_set 终态 | §3 节点 6,8 |
| M12 | Pipeline 解耦 | §6 / §9.3 |
| M13 | 游标恢复 | §6 |
| M14 | summary 压缩 | §3 节点 7 |
| M15 | MemPalace 召回 | §3 节点 3 / §9.5 |

## 附录 C：调试技巧

- `LANGCHAIN_TRACING_V2=true` + LangSmith 看每个节点的 input/output。
- 不想接 LangSmith 时，给每个节点开头加 `print(f"[{node}] msgs={len(state['messages'])}")` 是最朴素也最有效的。
- LangGraph 的 `graph.get_graph().print_ascii()` 能把图结构画到终端。
- PG 调试：`psql $PG_DSN -c "TABLE web_chat_pipeline_chunk LIMIT 20"` 看序号是否单调递增。

## 附录 D：和原报告的映射读法

每个 M 末尾的「对应原报告」指向报告里 §X 小节。建议每攻下一个 M，回去把对应章节再扫一遍——这时你**实际写过代码**，再读会发现报告里很多细节（如 `_llm_with_result_set` 这种命名）都能落地为你刚敲过的那个分支。



