# 对话里「贴代码」的格式规范（给 Agent / 协作者）

本文约定：在跟写里程碑、排障或方案说明时，**如何在对话里贴代码**才便于对照仓库、减少误贴与漏项。被协作者忽略或未按此执行的说明，容易造成「口头有、仓库无」的偏差；**本文件与里程碑代码同属项目资产，应纳入 Git 维护**（与「只口头说、不落盘」区分）。

---

## 1. 总原则

| 原则 | 说明 |
|------|------|
| **路径写全** | 使用从仓库根起的相对路径，如 `app/runtime/nodes.py`，避免只说「nodes 里改一下」。 |
| **新建 vs 续写** | 每个文件块标题必须标明 **`[新建]`** 或 **`[续写]`**；续写须说明是「整文件替换」「仅替换某函数」还是「在文件末尾追加」。 |
| **代码块独立** | 每个文件一个 fenced 代码块；块内为**当前推荐完整内容**（新建=整文件；续写=替换片段或追加片段，边界写清）。 |
| **块下必有解说** | **每个**代码块下方用简短自然语言说明：用途、与上下文件关系、注意点（环境、顺序、与指南差异等）。 |
| **非 Python 单列** | Shell、`.env` 示例、SQL 等单独成块，同样标注 `[续写]`/`[新建]` 若适用，并附解说。 |
| **与指南不一致时** | 若仓库刻意偏离 `docs/agent_skills_build_guide.md`（字段名、图结构），在解说里**显式写一句**，避免读者照搬指南覆盖本地设计。 |

---

## 2. 文件状态标签（标题行必写）

```text
### `相对/路径/文件名.ext` —— [新建]
```

或

```text
### `相对/路径/文件名.ext` —— [续写]（说明：在文件末尾追加 / 仅替换某某函数 / 整文件替换）
```

---

## 3. 代码块下方「解说」写什么（ checklist ）

建议至少覆盖其中几项（不必长段落）：

1. **做什么**：该文件/片段在本轮任务中的职责。  
2. **依赖**：依赖哪些同轮其它文件、环境变量、端口。  
3. **顺序**：是否必须先于某文件应用（例如先建包再 import）。  
4. **验证**：如何一条命令或一个动作验绿（可指向 README 或指南对应节）。  
5. **已知限制**：例如「M5 尚未接 ToolNode，仅能看到 tool_calls」。

---

## 4. 示例：一轮「只贴代码」应答应长什么样（模板）

以下示例主题：**M5 第一个 Tool `Read`（与指南一致，不接 ToolNode）**。仅作**格式示范**；具体实现以仓库与指南为准。

---

### `app/tools/__init__.py` —— [新建]

```python

```

**解说**：空文件即可，使 `app.tools` 成为 Python 包，便于 `from app.tools.xxx import ...`。

---

### `app/tools/base.py` —— [新建]

```python
from __future__ import annotations

from langchain_core.tools import BaseTool

from app.tools.read_tool import ReadTool


def build_default_tools() -> list[BaseTool]:
    return [ReadTool()]
```

**解说**：集中返回默认工具列表，避免 `nodes` 与多个 tool 文件循环 import；后续里程碑可在此扩展注册逻辑。

---

### `app/tools/read_tool.py` —— [新建]

```python
# （此处省略：完整 ReadTool 实现见当轮对话或指南 M5 骨架）
```

**解说**：`BaseTool` + `args_schema`；`session_id` 在 M5 可固定 `demo`，M7 再改为从 `RunnableConfig` / `run_manager` 读取；路径必须限制在 `WORKSPACE_ROOT/<session_id>/` 下，防 `..`。

---

### `app/runtime/llm.py` —— [续写]（说明：在现有 `stream_messages` 之后**追加**，勿删 `get_llm` / `clear_llm_cache` / `stream_messages`）

```python
from collections.abc import Sequence

from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool


def get_llm_with_tools(tools: Sequence[BaseTool]) -> Runnable:
    return get_llm().bind_tools(list(tools))
```

**解说**：对 `get_llm()` 做 `bind_tools`，供 `llm_node` 使用；返回类型在 LangChain 中常为 `Runnable`，与 `BaseChatModel` 注解可能不完全一致，以运行与类型检查为准。

---

### `app/runtime/nodes.py` —— [续写]（说明：**替换**顶部 import 与 `llm_node`；增加模块级 `_TOOLS`）

```python
# 示例：import 与 llm_node 片段（非整文件）
from app.runtime.llm import get_llm_with_tools
from app.tools.base import build_default_tools

_TOOLS = build_default_tools()


async def llm_node(state: GraphState) -> dict:
    llm = get_llm_with_tools(_TOOLS)
    ai = await llm.ainvoke(state["messages"])
    return {"messages": [ai]}
```

**解说**：与当前仓库一致时保留 **`await ... ainvoke`**，以满足 M4 起 `astream_events` 对异步调用的要求；勿在 M5 阶段接 `ToolNode`（属 M6）。

---

### Shell（准备测试数据）—— [非文件，命令块]

```bash
mkdir -p /tmp/skills/demo/data
echo "hello world" > /tmp/skills/demo/data/a.txt
```

**解说**：与 `.env` 中 `WORKSPACE_ROOT` 及 `ReadTool` 中固定 `demo` 会话一致；若本机 `WORKSPACE_ROOT` 不同，应改路径。

---

## 5. 本轮（建立本文档）起到了什么作用

| 作用 | 说明 |
|------|------|
| **统一贴码格式** | 以后对话中「新建 / 续写」一眼可辨，减少整文件误贴、漏贴 import 或搞反应用顺序。 |
| **强制块后解说** | 降低「只给代码不给语境」导致的误用（例如 M5 与 M6 边界、与指南字段名差异）。 |
| **与 Git 的关系** | 本文档**纳入版本库**（`docs/code-response-convention.md`），与「只在聊天里说过、仓库里找不到」区分；后续若调整贴码约定，应改本文并随里程碑或独立提交说明。 |
| **对齐最近一轮实践** | 第四节以 M5「只贴代码」为例，复用了最近一次对话中的结构（`tools` 包、`get_llm_with_tools`、nodes 续写方式等），便于对照复盘。 |

---

## 6. README 维护提示

在 [README.md](../README.md) 的「里程碑与正式代码路径」或「文档依据」中，可增加一条指向本文的链接，便于新协作者与 Agent 遵守同一套贴码约定。（若尚未添加链接，可在下次改 README 时补上。）
