# Caker 基础知识手册

> 本文档整合了 caker 项目涉及的所有核心概念的官方文档要点。
> 按学习顺序分为四个阶段，每个阶段对应 caker 中一段代码。

---

## 第一阶段：FastAPI + 异步 Python

> caker 中你写的：`app/main.py`、`app/api/chat.py`、`app/config.py`

### 1. FastAPI 是什么

FastAPI 是一个 Python Web 框架。它的核心工作方式：

```python
from fastapi import FastAPI

app = FastAPI()                    # 创建应用实例

@app.get("/health")                # 装饰器：声明 HTTP 方法 + 路径
async def health():                # 路径操作函数
    return {"ok": True}            # 返回 dict → FastAPI 自动转 JSON
```

**运行**：`uvicorn app.main:app --reload`（`main:app` = 模块名 `main` 里的变量 `app`）。

**自带文档**：启动后访问 `/docs`（Swagger UI）和 `/redoc`（ReDoc），自动生成交互式 API 文档。

### 2. 路径参数与请求体

```python
# 路径参数：URL 里的动态部分
@app.get("/users/{user_id}")
async def get_user(user_id: int):        # 类型注解 → 自动校验 + 转换
    return {"user_id": user_id}

# 请求体：POST 的 JSON body
from pydantic import BaseModel

class Item(BaseModel):
    name: str
    price: float

@app.post("/items")
async def create_item(item: Item):       # Pydantic model → 自动解析 JSON
    return item
```

FastAPI 根据参数的类型注解自动区分"这是路径参数还是请求体"。

### 3. Pydantic 模型

Pydantic 是 FastAPI 内置的数据校验库。你 caker 中所有输入/输出模型都基于它：

```python
from pydantic import BaseModel, Field

class ChatGraphIn(BaseModel):
    message: str
    session_id: str | None = None        # 可选字段

class ChatGraphOut(BaseModel):
    reply: str
```

`Field()` 提供更精细的控制：

```python
class ReadInput(BaseModel):
    rel_path: str = Field(..., description="相对路径")
    offset: int = Field(0, ge=0)         # 默认值 0，必须 ≥ 0
    limit: int = Field(200, ge=1, le=2000)  # 必须在 1～2000 之间
```

`...` 表示必填（`Ellipsis`）。

### 4. `async` / `await` 基础

Python 的异步编程核心概念：

```python
# 普通函数：调用即执行，阻塞等待
def sync_func():
    result = requests.get(url)   # 阻塞：等待网络返回
    return result

# 异步函数：可以"暂停"，让出 CPU 给其他任务
async def async_func():
    result = await http_client.get(url)  # await：在这里暂停，去干其他事
    return result
```

**为什么 caker 需要 async**：`llm_node` 调用 LLM API 时，网络 I/O 可能耗时数秒。`async` 让图引擎在等待 LLM 回复时不阻塞整个服务。`await` 的意思是"在这里暂停，等这个调用完成再继续往下走"。

```python
# caker 中的实际例子
async def llm_node(state: GraphState) -> dict:
    llm = get_llm_with_tools(_TOOLS)
    ai = await llm.ainvoke(state["messages"])   # 暂停等待 LLM 回复
    return {"messages": [ai]}
```

### 5. `async for` —— 异步迭代

```python
# 普通 for：遍历列表，每次拿一个元素
for item in [1, 2, 3]:
    print(item)

# async for：遍历异步流，每个元素需要 await
async for token in llm.astream(messages):
    print(token)          # 每个 token 都是异步到达的
```

`astream` 是流式调用——LLM 每吐出一个 token 就立刻返回，而不是等整段话说完。`async for` 逐个消费这些 token。你 caker 的 `/stream` 端点就在做这个。

### 6. 生成器与 `yield`

```python
# 生成器函数：用 yield 代替 return，每次 yield 返回一个值，然后暂停
def gen():
    yield "第一段"
    yield "第二段"
    yield "第三段"

for chunk in gen():
    print(chunk)
# 输出：第一段  第二段  第三段
```

`StreamingResponse` 需要一个生成器：每次 `yield` 一段 SSE 数据，客户端立刻收到一段。

```python
# caker 的 /stream 中
async def gen():
    async for ev in iter_graph_stream_events(...):
        yield sse_pack("delta", {"text": content})   # 推送给客户端
    yield sse_pack("done", {})
```

### 7. SSE（Server-Sent Events）

SSE 是 HTTP 长连接协议。服务端持续推送数据，格式为：

```
event: delta
data: {"text": "你好"}

event: done
data: {}
```

每条消息的结构：`event: <类型>\ndata: <JSON>\n\n`。最后那个空行（`\n\n`）是分隔符——客户端靠它识别一条消息的结束。你 caker 的 `sse_pack()` 函数就是在拼这个格式：

```python
def sse_pack(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode("utf-8")
```

客户端用 `EventSource`（浏览器）或 `curl -N` 逐条接收。

---

## 第二阶段：LangGraph 核心概念

> caker 中你写的：`app/runtime/graph.py`、`nodes.py`、`state.py`、`routes.py`

### 8. StateGraph —— 状态图

LangGraph 的核心抽象：**把程序的每个步骤建模为"节点"，步骤之间的流转建模为"边"，所有节点共享一个 State**。

```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

# 1. 定义共享状态
class MyState(TypedDict):
    messages: list
    result: str

# 2. 定义节点（每个节点是一个函数）
def node_a(state):
    return {"messages": ["hello"]}     # 返回要更新的字段

def node_b(state):
    return {"result": "done"}

# 3. 建图
g = StateGraph(MyState)
g.add_node("a", node_a)
g.add_node("b", node_b)
g.add_edge(START, "a")      # 开始 → 节点 a
g.add_edge("a", "b")        # 节点 a → 节点 b
g.add_edge("b", END)        # 节点 b → 结束

graph = g.compile()          # 编译为可执行图
result = graph.invoke({"messages": [], "result": ""})
```

LangGraph 自动管理：按边的顺序调节点、节点的返回值自动合并到共享 State、最后返回完整的 State。

### 9. `Annotated` 与 `add_messages` —— 消息列表自动追加

caker 的 `GraphState` 中 `messages` 字段用了 `Annotated`：

```python
from typing import Annotated
from langgraph.graph import add_messages

class GraphState(TypedDict):
    messages: Annotated[list, add_messages]
```

`**Annotated` 是什么**：Python 标准库 `typing.Annotated`。语法是 `Annotated[基础类型, 元数据1, 元数据2, ...]`。第一项是实际类型，后面的项是**附加信息**——不影响运行时类型，但框架可以读取这些元数据来做特殊处理。

在这里，`Annotated[list, add_messages]` 的意思是：类型是 `list`，附加元数据是 `add_messages`（一个 reducer 函数）。LangGraph 读到这个 reducer 后，就不会用"覆盖"的方式更新 messages，而是用 `add_messages` 函数把新消息**追加**到已有列表后面。

这就是为什么 `inject_system_node` 返回 `[SystemMessage(...)]`、`inject_user_node` 返回 `[HumanMessage(...)]`——它们每轮追加，不会互相覆盖。同样的，`llm_node` 返回的 `[AIMessage(...)]` 和 `ToolNode` 返回的 `ToolMessage(...)` 也是追加，不会把之前的对话删掉。

### 10. 条件边 —— 根据 state 决定走向

```python
g.add_conditional_edges(
    "llm",                    # 从哪个节点出发
    route_after_llm,          # 路由函数：接收 state，返回字符串
    {
        "tools": "tools",     # 路由函数返回 "tools" → 走去 tools 节点
        "end": "end",         # 路由函数返回 "end" → 走去 end 节点
    },
)
```

路由函数就是一个普通的 Python 函数：

```python
def route_after_llm(state):
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tools"       # LLM 要调工具 → 去 tools
    return "end"             # LLM 直接回复 → 结束
```

### 11. ToolNode —— 工具执行与回灌

`ToolNode` 是 LangGraph 预置的节点。它自动完成：

1. 从 `state["messages"]` 的最后一条 `AIMessage` 中提取 `tool_calls` 列表
2. 对每个 `tool_call`，找到匹配的工具实例（按 `tool.name` 匹配）
3. 将 `tool_call["args"]` 解包为关键字参数，调用 `tool._run(**args, run_manager=...)`
4. 将返回值包装成 `ToolMessage(content=返回值, tool_call_id=...)`
5. 将 `ToolMessage` 追加到 messages

**参数传递链路（以 `call_skill` 为例）**：

```
LLM 输出 AIMessage(tool_calls=[{"name":"call_skill", "args":{"skill_name":"hello_skill"}}])
        │
        ▼
ToolNode:
  1. 找到 name="call_skill" 的工具实例 → CallSkillTool()
  2. 解包 args → tool._run(skill_name="hello_skill", run_manager=<自动注入>)
        │                              ↑ LLM 决定的              ↑ LangGraph 注入
  3. 返回值 → ToolMessage(content='{"skill_name":"hello_skill",...}')
  4. 追加到 messages
```

**你只需要做两步**：

```python
from langgraph.prebuilt import ToolNode

_TOOLS = [ReadTool(), CallSkillTool(), RunPyScriptTool()]   # 工具列表
tools_node = ToolNode(_TOOLS)                               # 创建 ToolNode

# 图中连接
g.add_node("tools", tools_node)
g.add_edge("tools", "llm")          # 工具执行后回 llm 继续推理
```

`**llm → tools → llm` 循环**：LLM 输出 tool_call → ToolNode 执行工具 → ToolMessage 回灌 → LLM 看到结果继续推理。如果没有更多 tool_call，路由到 end。

### 12. LLM 怎么知道有哪些工具

通过 `bind_tools`：

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o-mini", ...)
llm_with_tools = llm.bind_tools([ReadTool(), CallSkillTool()])
```

`bind_tools` 把工具的参数 schema（Pydantic model）转成 LLM 能理解的 JSON Schema，追加到请求中。LLM 看到后就知道"我可以调用 `Read(rel_path=..., offset=..., limit=...)`"。它自己决定要不要调、调哪个、传什么参数。

### 13. `ainvoke` vs `astream_events`

```python
# ainvoke：等 LLM 完整回复，一次返回最终 state
result = await graph.ainvoke(inputs, config=config)

# astream_events：逐事件返回，能拿到每个 token、每个节点执行
async for event in graph.astream_events(inputs, config=config, version="v2"):
    if event["event"] == "on_chat_model_stream":
        chunk = event["data"]["chunk"]
        print(chunk.content)       # 一个一个 token 实时输出
```

caker 的非流式端点用 `ainvoke`，流式端点用 `astream_events`。

---

## 第三阶段：LangChain 工具与 LLM

> caker 中你写的：`app/runtime/llm.py`、`app/tools/read_tool.py`

### 14. ChatOpenAI —— LLM 客户端

`langchain-openai` 的 `ChatOpenAI` 不只连接 OpenAI，只要 `base_url` 指向 OpenAI 兼容接口即可：

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="qwen3.5-397b-fp8",           # 模型名
    api_key="sk-...",                    # API 密钥
    base_url="https://your-gateway/v1",  # 兼容端点
    temperature=0.7,                     # 输出随机性（0=确定，2=随机）
)
```

temperature 含义：`0` 表示每次相同输入获得几乎相同输出（适合工具调用和推理）；`0.7` 表示有一定随机性（适合创作和闲聊）。

caker 中用了 `@lru_cache` 缓存 LLM 实例：

```python
from functools import lru_cache

@lru_cache(maxsize=8)
def get_llm():
    return ChatOpenAI(...)
```

`@lru_cache` 是 Python 标准库的缓存装饰器。第一次调用 `get_llm()` 时创建 LLM 实例并缓存；后续调用直接返回缓存的实例，不会重复创建。这避免了每次请求都重新建立 HTTP 连接。

### 15. BaseTool —— 自定义工具（续）：动态过滤工具列表

M11 的 `result_set` 工具有一个特殊行为：**在流式请求中不暴露给 LLM**。因为流式请求通过 SSE 逐 token 返回结果，不需要一个"正式交卷"的工具。非流式请求则需要 `result_set` 来正式产出最终回答。

```python
def build_default_tools(*, include_result_set: bool = False) -> list[BaseTool]:
    tools = [ReadTool(), CallSkillTool(), RunPyScriptTool()]
    if include_result_set:
        tools.append(ResultSetTool())
    return tools
```

非流式端点传 `include_result_set=True`，流式端点传 `False`。这个模式叫**按场景过滤工具**——不是所有工具在所有请求中都适用。

一个工具 = 名称 + 描述 + 参数 schema + 执行函数：

```python
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

class MyToolInput(BaseModel):
    query: str = Field(..., description="搜索关键词")

class MyTool(BaseTool):
    name: str = "my_search"
    description: str = "搜索信息"
    args_schema: type[BaseModel] = MyToolInput

    def _run(self, query: str, *, run_manager=None, **_) -> str:
        # 参数 query 由 LLM 传入，run_manager 由 LangGraph 传入
        result = do_search(query)
        return result
```

**关键点**：

- `name`：LLM 在 tool_call 里用的名字
- `description`：帮助 LLM 理解"什么时候该用这个工具"
- `args_schema`：告诉 LLM 这个工具需要哪些参数、什么类型
- `_run()` 的 `query`：与 `MyToolInput.query` 对应，LLM 决定传什么值
- `_run()` 的 `run_manager`：LangGraph 自动注入，不从 LLM 来

---

## 第四阶段：检查点、上下文管理器、SQLite

> caker 中你写的：`app/runtime/graph.py`（M10）、`app/main.py`（lifespan）

### 16. 检查点是什么

检查点 = 图引擎在每一步执行后自动保存状态快照。下一次同一会话的请求进来时，自动恢复。

```python
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import StateGraph

g = StateGraph(MyState)
# ... 加节点、加边 ...

async with AsyncSqliteSaver.from_conn_string("state.db") as checkpointer:
    await checkpointer.setup()       # 建表
    graph = g.compile(checkpointer=checkpointer)
    # checkpointer 负责在每步自动存盘 / 恢复

# 调用时传 thread_id
config = {"configurable": {"thread_id": "session-abc"}}
graph.invoke({"messages": []}, config=config)
```

**工作原理**：

1. 执行 `graph.invoke(inputs, config)` 时，LangGraph 先查 `var/state.db`：`thread_id="session-abc"` 有没有上次的 messages？
2. 有 → 恢复 messages 列表；没有 → 从 `inputs["messages"]`（空列表）开始
3. 每执行一个节点，自动把当前 messages 写入 `var/state.db`
4. 下次同一个 `thread_id`，自动从上次的 messages 继续

`**thread_id` 和 `session_id` 的关系**（caker 特有）：

```python
config = {"configurable": {
    "session_id": "abc123",    # 给 WorkspaceManager 用，决定读写哪个沙箱目录
    "thread_id": "abc123",     # 给 checkpointer 用，决定用哪份对话历史
}}
```

caker 中两者值相同，但语义分开：前者控制文件系统隔离（M7），后者控制对话记忆（M10）。LangGraph 只认 `thread_id`，不认 `session_id`——所以 M10 必须两个都传。

**你不用写任何 save/load 代码。** 编译时传 checkpointer，调用时传 thread_id，LangGraph 在幕后全自动处理。

### 17. `async with` —— 异步上下文管理器

```python
# 普通 with：打开文件，自动关闭
with open("file.txt") as f:
    data = f.read()
# 退出 with 块时，f.close() 自动调用

# async with：异步打开资源，异步关闭
async with AsyncSqliteSaver.from_conn_string("state.db") as checkpointer:
    # 进入：打开数据库连接
    graph = build_graph().compile(checkpointer=checkpointer)
    # ...使用 graph...
# 退出：自动关闭数据库连接
```

`async with` 和 `with` 的区别只有一个：进入和退出时允许 `await`。对于数据库连接这类"需要网络/文件 I/O 的连接"，必须用 `async with`。

### 18. `@asynccontextmanager` —— 把函数变成上下文管理器

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def my_context():
    print("进入")      # ① 进入时执行
    yield              # ② 暂停，让外部代码运行
    print("退出")      # ③ 退出时执行（即使异常也会执行）
```

`yield` 把函数分成两半：

- `yield` 之前：`async with` 进入时执行
- `yield` 之后：`async with` 退出时执行

### 19. FastAPI Lifespan —— 启动/关闭钩子

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.runtime.graph import compile_graph

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ===== 启动时执行 =====
    Path("var").mkdir(exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string("var/state.db") as cp:
        await cp.setup()
        compile_graph(cp)       # 存入模块级全局变量 _compiled
        yield                   # ← 暂停，应用开始接受请求
    # ===== 关闭时执行 =====
    # async with 退出时自动关闭 SQLite 连接

app = FastAPI(lifespan=lifespan)
```

caker 中 `compile_graph(checkpointer)` 在 `graph.py` 里实现。它把编译后的图存入模块级全局变量 `_compiled`。运行时 `chat.py` 通过 `get_graph()` 取这个全局变量——保证 lifespan 初始化完成后所有请求拿到的都是带检查点的编译图。

**为什么不能直接在模块顶层编译**：`AsyncSqliteSaver.from_conn_string()` 返回的是 async context manager，必须在 `async with` 里用。`async with` 必须在 `async def` 函数里用。模块顶层不能 `await`。Lifespan 是 FastAPI 提供的"唯一的 async def 初始化入口"。

### 20. SQLite 是什么

SQLite 是一个**文件级数据库**。和 PostgreSQL 的核心区别：


|     | SQLite           | PostgreSQL  |
| --- | ---------------- | ----------- |
| 形态  | 一个文件（`state.db`） | 独立服务器进程     |
| 启动  | 打开文件即用           | 需要启动服务、配置用户 |
| 依赖  | Python 标准库自带     | 需要安装 pg 驱动  |
| 适合  | 本地单用户            | 多用户高并发      |


caker M10 的 `var/state.db` 就是一个 SQLite 文件。`AsyncSqliteSaver` 在里面建表，存每个 `thread_id` 的对话历史。你删除 `var/state.db` → 所有会话记忆丢失；保留 → 重启 uvicorn 后记忆还在。

---

---

## 第五阶段：图引擎进阶 — summary 节点（M14 依赖）

> caker M14 的目标：当对话历史过长时，用一个额外的 LLM 调用将历史压缩成摘要，避免超出模型上下文限制。

### 21. 为什么需要 Summary 节点

LLM 有一个硬性的上下文窗口限制（最大输入 token 数）。随着多轮对话积累，`messages` 列表可能包含几十条 SystemMessage、HumanMessage、AIMessage、ToolMessage。一旦超出模型的最大输入，请求会失败。

Summary 节点的作用：**在 messages 快要超出限制时，自动将历史压缩成一段精炼的摘要**。

```
原来（messages 可能很长）：
  SystemMessage("你是Caker...") → HumanMessage("我叫张三") → AIMessage("好的张三") →
  HumanMessage("帮我分析数据") → AIMessage(tool_call: Read) → ToolMessage("...") →
  AIMessage("数据如下...") → HumanMessage("继续分析") → ...

Summary 压缩后：
  SystemMessage("你是Caker...") →
  HumanMessage("这是之前对话的摘要：用户叫张三，上一轮在分析某数据文件，结论是...") →
  HumanMessage("继续分析")  ← 本轮新输入
```

**核心权衡**：压缩会丢失细节（比如工具返回的具体数据），但能保住对话的连贯性（知道之前聊了什么话题）。

### 22. Summary 节点的实现思路

Summary 节点本质是图引擎的一次内部 LLM 调用：

```python
async def summary_node(state: GraphState) -> dict:
    # 1. 取 messages（太长，需要压缩）
    old_messages = state["messages"]

    # 2. 构造一个"要求 LLM 摘要"的消息
    summary_prompt = HumanMessage(
        content="请用中文简要总结以上对话的关键信息，包括用户身份、讨论主题、工具调用结果。"
    )

    # 3. 调 LLM 生成摘要（不带 tools，只是一个普通的 LLM 调用）
    llm = get_llm()                    # 不带 bind_tools
    summary = await llm.ainvoke(old_messages + [summary_prompt])

    # 4. 用摘要替换原来的 messages
    return {
        "messages": [summary],         # 替换，不是追加
    }
```

注意这里必须**替换**而不是追加 messages——如果只是追加，messages 会越来越长。`summary` 返回 `{"messages": [摘要]}` 没有 `add_messages` reducer 会覆盖整个 messages 列表，这正是我们想要的效果。

### 23. 在图中接入 Summary

和 M10 的 `route_after_start` 一样的模式：

```python
# 图中增加 summary 节点
g.add_node("summary", nodes.summary_node)

# inject_user 之后、llm 之前，加一条条件边
g.add_conditional_edges(
    "inject_user",
    routes.route_before_llm,        # 新路由：判断是否过长
    {
        "llm": "llm",               # 正常 → 直接 LLM
        "summary": "summary",       # 过长 → 先压缩
    },
)
g.add_edge("summary", "llm")        # 压缩后回 LLM
```

路由函数（概念）：

```python
def route_before_llm(state):
    total_chars = sum(len(str(m)) for m in state["messages"])
    if total_chars > 50000:        # 超过一定字符数
        return "summary"
    return "llm"
```

图结构变为：

```text
inject_user ──route_before_llm──┬→ llm
                                └→ summary → llm
```

---

## 第六阶段：向量数据库与嵌入（M15 依赖）

> caker M15 的目标：MemPalace + ChromaDB，实现跨会话语义记忆。让 Agent 在下一轮新会话中仍能"记住"之前的重要信息。

### 24. 嵌入（Embedding）是什么

LLM 处理的是文本，但计算机只能做数学运算。**嵌入**就是把一段文本转换成一个数字列表（向量）的过程。这个向量携带了文本的语义信息。

```
"我喜欢编程" → 嵌入模型 → [0.12, -0.34, 0.78, ..., 0.05]  （通常 768 或 1536 个数字）
"我喜欢写代码" → 嵌入模型 → [0.13, -0.32, 0.76, ..., 0.06]  （和上面很接近）
"今天天气不错" → 嵌入模型 → [-0.45, 0.89, -0.12, ..., 0.71]  （和上面差距很大）
```

**核心性质**：语义相近的文本，向量也相近。计算两条文本的相似度，只需计算它们向量的余弦相似度或欧氏距离。

### 25. ChromaDB 是什么

ChromaDB 是一个专门存储和检索嵌入向量的数据库。它的核心操作：

```python
import chromadb

client = chromadb.Client()

# 创建一个collection（相当于关系数据库里的"表"）
collection = client.create_collection("memories")

# 存记忆：每条记忆 = 文本 + 元数据 + 唯一ID
collection.add(
    documents=["我叫张三", "我喜欢Python"],        # 原始文本
    metadatas=[{"source": "chat"}, {"source": "chat"}],  # 附加信息
    ids=["mem1", "mem2"],                           # 唯一ID
)

# 搜记忆：输入一段文本，返回语义最接近的记忆
results = collection.query(
    query_texts=["我喜欢的编程语言是什么？"],
    n_results=2,                   # 返回最相似的2条
)
# results 会包含 "我喜欢Python"（语义匹配），而不是 "我叫张三"
```

**ChromaDB 和 SQLite 的关系**：ChromaDB 在本地模式下**用 SQLite 存元数据**（文本、id、时间戳等），用**自己的向量索引**（hnswlib）存嵌入向量。SQLite 管"这条记忆是什么时候创建的"，向量索引管"哪条记忆语义最接近"。

### 26. LangChain 的嵌入模型

caker 需要嵌入模型来把文本转成向量。`langchain-openai` 提供嵌入模型接口：

```python
from langchain_openai import OpenAIEmbeddings

embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",    # 嵌入模型
    api_key="sk-...",
    base_url="https://your-gateway/v1",
)

# 把文本转为向量
vector = embeddings.embed_query("我喜欢Python")
# → [0.012, -0.034, ..., 0.045]  （768维或1536维的列表）
```

---

## 附录：caker 项目文件与概念对照


| caker 文件                          | 用到的核心概念                                                                                 | 所在里程碑            |
| --------------------------------- | --------------------------------------------------------------------------------------- | ---------------- |
| `app/main.py`                     | FastAPI 应用、lifespan、`@app.get("/health")`                                               | M0/M10           |
| `app/config.py`                   | Pydantic Settings、`BaseSettings`                                                        | M0               |
| `app/api/chat.py`                 | `APIRouter`、`BaseModel`、`StreamingResponse`、yield、`async for`、动态工具过滤                    | M1–M4/M7/M11     |
| `app/runtime/state.py`            | TypedDict、`Annotated`、`add_messages`                                                    | M3               |
| `app/runtime/graph.py`            | `StateGraph`、`add_edge`、`add_conditional_edges`、`compile`、`astream_events`、checkpointer | M3/M4/M6/M10/M14 |
| `system_prompt.md`                | 系统提示词模板（`{skills_meta}`）；由 `SkillManager.render_system_prompt()` 注入                  | M8+              |
| `app/skills/manager.py`           | 技能索引 + `load_system_prompt` / `render_system_prompt`                                      | M8+              |
| `app/runtime/nodes.py`            | 节点函数、`inject_system_node`、`ToolNode`、summary 节点（M14）                                  | M3–M8/M14        |
| `app/runtime/routes.py`           | 条件路由函数、`route_after_llm`、`route_after_start`、`route_before_llm`                         | M6/M10/M14       |
| `app/runtime/llm.py`              | `ChatOpenAI`、`bind_tools`、`lru_cache`、嵌入模型                                              | M2/M5/M15        |
| `app/runtime/sse.py`              | SSE 协议、`event:` / `data:` / `\n\n`                                                      | M4               |
| `app/tools/read_tool.py`          | `BaseTool`、`args_schema`、`_run()`、`run_manager`                                         | M5/M7            |
| `app/tools/call_skill_tool.py`    | `BaseTool`、JSON 序列化                                                                     | M8               |
| `app/tools/run_py_script_tool.py` | `BaseTool`、`subprocess.run`、`try/except`                                                | M9               |
| `app/workspace/manager.py`        | `Path.resolve()`、`relative_to`、`symlink_to`、符号链接                                        | M7/M9            |
| `app/skills/manager.py`           | 文件扫描、YAML front matter、正则表达式                                                            | M8               |
| `app/summary/handler.py`          | Summary 节点实现、LLM 内部调用、messages 替换                                                       | M14              |
| `app/mempalace/chroma_store.py`   | ChromaDB 客户端、collection 管理、`add`/`query`                                                | M15              |
| `app/mempalace/injector.py`       | 语义召回、记忆注入到 messages                                                                     | M15              |


---

> **学习建议**：按阶段顺序读。每读完一个阶段，去 caker 仓库找对应的代码，确认"这是我写的那行"。
> 不需要一次全懂。`async`/`await` 和 LangGraph 检查点是两个最大的坎，反复看几遍。

