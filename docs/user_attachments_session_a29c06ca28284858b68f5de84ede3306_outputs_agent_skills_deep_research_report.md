# Agent Skills 框架深度研究报告（基于代码阅读）

> 研究对象：Agent Skills 运行时框架（运行环境内代码）
> 研究方式：直接阅读 `/app/web_chat/` 下核心源码，结合运行时行为分析
> 日期：2026-05-08

---

## 1. 摘要

Agent Skills 并非一个简单的 LLM 工具调用封装，而是一个构建在 **LangGraph** 之上的完整 **Agent 操作系统**。它为 AI 提供了进程模型（Session）、文件系统沙箱（Workspace）、可扩展工具链（14+ Tool）、长期记忆（MemPalace/ChromaDB）以及严格的路由图引擎。

框架核心设计遵循三条原则：
1. **图引擎驱动一切**：所有 LLM 交互、工具执行、结果判定均在预定义的 StateGraph 中按节点流转
2. **技能即子图**：每个技能（Skill）是通过 `call_skill` 动态加载的 SKILL.md，按需注入 LLM 上下文
3. **生产者-消费者解耦**：LLM 执行与 HTTP SSE 连接通过 PipelineService（PG 日志 + asyncio.Queue）彻底分离

---

## 2. 整体架构：四层模型

从功能边界将框架分为四个层级：

### 第一层 · 核心运行时（约 2000 行 Python）

这是最小可用系统的全部内容，能独立跑通「用户输入 → LLM 推理 → 工具调用 → 流式输出」的闭环。

| 组件 | 核心文件 | 行数 |
|------|---------|------|
| SkillsRuntime（StateGraph 引擎） | `skills_runtime.py` | 2134 |
| SkillsManager（技能注册与加载） | `skills_manager.py` | 300 |
| WorkspaceManager（会话沙箱） | `workspace_manager.py` | 305 |
| 工具集（14+ Tool） | `tools/` 目录 | ~2000 |
| FastAPI 接入层 | `server.py` | 514 |

### 第二层 · 会话与持久化

| 组件 | 核心文件 | 功能 |
|------|---------|------|
| PipelineService | `pipeline.py` (814行) | SSE 生产者-消费者解耦 |
| StateStore | `state_store.py` (502行) | S3/PG 状态检查点 |
| SummaryHandler | `summary/handler.py` | 长上下文自动压缩 |

### 第三层 · 认证与用户

IAM 中间件（用户身份注入）、飞书 OAuth（令牌授权）、用户技能合并（不同用户加载不同技能集）。

### 第四层 · 运维与前端

K8s Helm Chart 部署、Docker Compose 本地开发、React + TypeScript SPA 前端。

---

## 3. 图引擎详解：8 个节点的执行流

这是整个框架的大脑。StateGraph 继承 LangGraph 的 `MessagesState`，额外增加了 `result_text`、`result_set_handled`、`skip_inject_system`、`streaming`、`mempalace` 等状态字段。

### 节点 1：start（异步）

按 `session_id` 从 S3（file 模式）或 PostgreSQL（pgsql 模式）加载上一轮对话历史。若加载到历史 → 设置 `skip_inject_system=True`，将历史消息与当前用户输入合并。同时剥离历史中的 `result_set` 消息，避免新轮次误判。

**关键实现**：`_start_node()` 调用 `StateStore.load_from_s3()` 或 `load_previous_run()`。

### 节点 2：inject_system（同步）

在会话开头注入系统提示词，包括：
- 当前日期/时间/时区
- 会话工作区路径规范（Bash 需绝对路径）
- 用户上下文（IAM 用户详情）
- Skills 系统提示词（从 `skills_system_prompt.md` 加载）
- MemPalace 使用说明
- 界面语言强约束段落
- 可用 Skills 列表（JSON 元数据，不含 SKILL.md 正文）

当 `skip_inject_system=True` 时此节点被跳过。

### 节点 3：mempalace_inject（同步）

在 LLM 调用前注入 MemPalace 引导 Human 消息（JSON），包含 wakeup 文本和强制召回判定结果。通过 `mempalace_mgr.should_inject_mempalace_bootstrap()` 判断是否需要注入，若上条消息非用户 Human 则不重复注入。

### 节点 4：llm（同步，run_in_executor）

调用 LLM（`llm_with_tools.invoke()`），传入当前消息列表。返回 `AIMessage`（可能含 `tool_calls`）。

关键设计细节：
- **多模型动态切换**：按 `configurable.llm_model` 从缓存字典 `_llm_by_model_id` 获取对应 `BaseChatModel` 实例，懒创建
- **流式/非流式区分**：流式请求用 `llm_with_tools`（不含 result_set 工具），非流式用 `_llm_with_result_set`（含 result_set）
- **错误容错**：JSON 解析异常 → 降级重试（不带 tools）；通用异常 → 返回友好错误 AIMessage

### 节点 5：tools（同步，run_in_executor）

LangGraph 标准 `ToolNode`，根据 AIMessage 中的 `tool_calls` 执行对应工具。工具列表通过 `_get_tools_for_state()` 根据 streaming 状态动态选择。

### 节点 6：apply_result_set（同步）

解析 tools 节点后的消息，检查是否包含 `result_set` 工具调用结果。若是，提取 `result_text` 写入 state，标记 `result_set_handled=True`。

### 节点 7：summary（异步）

当上下文 token 量超过阈值（由 `summary_cond_ratio * max_input_tokens` 计算），自动触发上下文压缩。使用 `RemoveMessage(REMOVE_ALL_MESSAGES)` + 压缩后列表写回 `messages`。

### 节点 8：end（异步）

将 `result_text` 追加到 `messages`，保存最终状态到 StateStore，触发 MemPalace auto_store 后台任务。

### 路由逻辑

| 路由函数 | 条件 | 目标 |
|---------|------|-----|
| `_route_after_start` | `skip_inject_system=True` | 直接到 `mempalace_inject` |
| | `skip_inject_system=False` | 到 `inject_system` → `mempalace_inject` |
| `_route_after_llm` | AIMessage 含 `tool_calls` | 到 `tools` |
| | 需提示 result_set 且未超最大尝试次数 | 到 `prompt_result_set` |
| | 其他 | 到 `end` |
| `_route_after_tools` | `result_set_handled=True` | 到 `end` |
| | token 超阈值 | 到 `summary` → `mempalace_inject` → `llm` |
| | 其他 | 到 `mempalace_inject` → `llm`（继续循环） |

---

## 4. 工具链：14+ 工具的完整矩阵

所有工具继承 LangChain `BaseTool`，通过 `bind_tools()` 与 LLM 绑定。

### 工具分类清单

| 类别 | 工具名 | 核心能力 |
|------|--------|---------|
| 技能调度 | `call_skill` | 按名加载 SKILL.md，返回 JSON |
| 文件系统 | `Read` | 按相对路径分页读取工作区文件 |
| | `Write` | 创建/覆盖写文件（session 隔离） |
| | `Edit` | 精确字符串匹配替换 |
| | `Glob` | 通配符查找文件 |
| 命令执行 | `Bash` | 执行 Shell 命令（需绝对路径） |
| | `RunPyScript` | 执行 skills/ 下 Python 脚本，注入 `SESSION_ID` / `USER_ID` |
| | `RunJsTsScript` | 执行 JS/TS 脚本（Node.js），TS 自动 tsx 转译 |
| 对象存储 | `S3Upload` | 上传文件/目录到 S3/OSS |
| | `S3Download` | 从 S3/OSS 下载到工作区 |
| | `FileDelivery` | 通过 S3 预签名 URL 向用户交付文件 |
| 长期记忆 | `MemPalaceSearch` | 语义搜索 ChromaDB 历史记忆 |
| | `MemPalaceStore` | 持久化到长期记忆 |
| | `MemPalaceStatus` | 查询记忆库状态 |
| | `MemPalaceL0Read` | 读取 L0 结构化记忆 |
| | `MemPalaceL0Write` | 写入 L0 结构化记忆 |
| 辅助 | `GetCurrentTime` | 获取当前时间（支持时区） |
| | `GetSshPublicKey` | 获取用户 SSH 公钥 |
| | `HtmlCanvas` | 读取 HTML 供前端内联渲染 |

### call_skill 工具：动态加载的核心

这是框架最精巧的设计之一。流程如下：

1. LLM 发出 `tool_call(name="call_skill", args={"skill_name": "charts"})`
2. `CallSkillTool._arun()` 通过 SkillsManager 查找技能，获取 SKILL.md 全文
3. 剥离 YAML front matter（`---` 之间的元数据），仅保留正文（操作说明）
4. 包装为 JSON（含 notice 字段，提醒 LLM 这不是用户文档而是操作说明）
5. 作为 `ToolMessage` 返回，LLM 在下一轮按操作说明执行

关键点：SKILL.md 内容仅在 call_skill 时加载，不预加载所有技能正文（节省 token）。

---

## 5. 工作区隔离：会话沙箱

每个会话拥有独立的工作区目录：`/tmp/skills/<session_id>/`

| 路径 | 权限 | 用途 |
|------|------|------|
| `/tmp/skills/<id>/skills/` | 只读（symlink） | 技能脚本与模板 |
| `/tmp/skills/<id>/outputs/` | 读写 | 用户产出文件 |
| `/tmp/skills/<id>/data/` | 读写 | 临时数据 |
| `/tmp/skills/<id>/books/` | 只读（symlink） | 参考书 |

安全约束：
- 所有工具通过 `resolve_workspace_path()` 做路径校验，禁止绝对路径、禁止 `..` 路径穿越
- `is_readonly_path()` 阻止对 skills/ 目录的写入
- 子进程通过 `SESSION_ID` / `USER_ID` 环境变量获知会话与用户标识

---

## 6. PipelineService：生产者-消费者解耦

这是框架最精巧的架构设计。传统 LLM 流式 API 中，SSE 连接与 LLM 执行强耦合——连接断开则执行中断。PipelineService 彻底解决了这一痛点。

### 核心机制

**生产者端**：`schedule_pipeline_turn()` 通过 `asyncio.create_task` 在事件循环中投递后台任务。任务内调用 `SkillsRuntime.aexecute()`，每条 SSE 行同时写入 PG 并广播到内存队列。

**PostgreSQL 持久化**：表 `web_chat_pipeline_chunk`（字段：session_id、seq、line、event_id、turn_id、created_at），按 (session_id, seq) 唯一约束。

**内存广播**：同一 session 的多个连接共享一个 `asyncio.Queue` 订阅列表。

**游标恢复**：支持 `after_seq`、`after_event_id`、`after_turn_id` 三种游标，用于断线重连和页面刷新恢复。

**自动结束**：`stop_after_producer_idle=True`（默认），当生产者完成且持久层无新数据时，消费端自动关闭 SSE。

### 两个消费者入口

| 入口 | 用途 |
|------|------|
| `POST /api/v2/stream` | 直接流式请求，生产者+消费同连接 |
| `POST /api/v1/sessions/{id}/pipeline` | 独立消费，断线重连 |

---

## 7. StateStore：状态持久化

全局单例模式。在 `start` 节点加载历史，在 `end` 节点保存 checkpoint。

支持两种后端：
- **S3（file 模式）**：序列化 messages 列表为 JSON，存储到 `skills_runtime_state/<session_id>/latest.json`
- **PostgreSQL（pgsql 模式）**：利用 LangGraph 的 `AsyncPostgresSaver`，将整个图状态 checkpoint 到 PG

配置控制：`skills_runtime.load_state: "file" | "pgsql"` 和 `skills_runtime.save_state: "file,pgsql"`（可同时保存两处）。

消息序列化通过 `_message_to_dict()` 和 `messages_from_serialized()` 处理，支持 HumanMessage、AIMessage、SystemMessage、ToolMessage 四种类型。

---

## 8. 完整请求生命周期

### 阶段 A：HTTP 接入
1. 前端发送 `POST /api/v2/stream`，携带用户消息和 session_id
2. FastAPI 中间件链：CORS → request_id 注入 → IAM 用户解析
3. 路由处理器调用 `schedule_pipeline_turn()` 投递后台任务

### 阶段 B：图初始化
4. `start` 节点按 session_id 从 StateStore 加载历史消息
5. 若有历史：合并历史 + 当前用户输入，设置 `skip_inject_system=True`
6. 若无历史：进入 `inject_system` 节点，注入完整系统提示词
7. `mempalace_inject` 追加 MemPalace 引导 JSON

### 阶段 C：LLM-工具循环
8. `llm` 节点调用 LLM，传入当前 messages 列表
9. LLM 返回 AIMessage。若含 `tool_calls`：路由到 `tools` 节点
10. `tools` 节点执行对应工具
11. `apply_result_set` 检查是否有 result_set 调用结果
12. 若无 result_set 且不需 summary：返回 `mempalace_inject` → `llm` 继续循环
13. 若 token 超阈值：进入 `summary` 节点做上下文压缩
14. 若 result_set 已完成：路由到 `end`

### 阶段 D：交付
15. `end` 节点将 result_text 写入 messages，保存 state 到 S3/PG
16. PipelineService 消费者将 SSE 行从 PG 日志读取并发送给前端

---

## 9. 核心设计模式总结

### 9.1 图引擎即编排器
LangGraph StateGraph 为 Agent 提供了一种声明式的「思考-行动-观察」循环，节点顺序和路由逻辑清晰且可测试。

### 9.2 call_skill 即动态加载
通过「LLM 按需加载 SKILL.md → 按操作说明执行脚本」的间接层，实现技能的热插拔和无限扩展。这与传统「硬编码 function calling」有本质区别。

### 9.3 Pipeline 即持久化日志
Kafka 风格的持久化日志 + 内存广播队列，让生产者（LLM 执行）与消费者（HTTP SSE）彻底解耦。这一设计解决了 SSE 连接不稳定带来的执行中断问题。

### 9.4 workspace 即沙箱
每个 session 独立的文件系统，配合 symlink 实现技能目录只读共享和安全隔离。

### 9.5 MemPalace 即长期记忆
基于 ChromaDB 的语义检索 + L0 结构化记忆的双层记忆架构，让 Agent 具备跨会话的个性化能力。

---

## 10. 分批实现路线

### 第一批：最小闭环（约 1-2 周）
- FastAPI Server + SkillsRuntime StateGraph（start → inject_system → llm → end）
- LLM 集成 + 基础 Tools（Bash + Read + Write）
- WorkspaceManager + SSE 流式输出
- Memory Checkpointer（进程内 MemorySaver）

产出：能通过 curl 发送消息并获得流式 SSE 响应的命令行 Agent。

### 第二批：技能系统（约 1 周）
- SkillsManager + call_skill 工具
- Skills 目录结构 + RunPyScript 工具

产出：支持动态加载 Skill 的 Agent，可通过创建新 skill.md 扩展能力。

### 第三批：持久化与管道（约 1-2 周）
- StateStore + S3 + PipelineService
- PostgreSQL Checkpointer + SummaryHandler + SessionManager

产出：生产可用的 Agent 服务，支持多轮长对话、断线恢复、多进程扩展。

### 第四批：认证与多用户（约 1 周）
- IAM 中间件 + 飞书 OAuth + 用户技能合并 + 用户 SSH 密钥

产出：多租户 Agent 平台。

### 第五批：长期记忆与运维（按需）
- MemPalace 全部工具 + 前端 SPA + K8s 部署 + 飞书业务技能

---

## 11. 结论

通过对核心源码的直接阅读（`skills_runtime.py`（2134行）、`pipeline.py`（814行）、`skills_manager.py`（300行）、`workspace_manager.py`（305行）、`state_store.py`（502行）、`call_skill_tool.py`（141行）等），可以确认以下核心事实：

1. **Agent Skills 是一个 LangGraph 上的 Agent 操作系统**，而非简单的 skill 调用封装
2. **图引擎是灵魂**：8 个节点 + 5 条路由规则的精炼 Agent 循环模式
3. **Pipeline 是最精巧的设计**：PG 日志 + 内存广播实现的生产者-消费者解耦
4. **call_skill 是动态扩展的关键**：让 LLM 按需加载操作说明，实现热插拔式技能扩展
5. **分层设计有利于渐进式实现**：核心运行时仅约 2000 行 Python 即可跑通最小闭环
