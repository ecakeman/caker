# Caker 设计理念

本文描述 Caker **是什么、不是什么**，以及我们做技术选型时的共同立场。实现细节见 [深度研究报告](user_attachments_session_a29c06ca28284858b68f5de84ede3306_outputs_agent_skills_deep_research_report.md)；里程碑落盘见 [milestones.md](milestones.md)。

## 一句话

**Caker 是在本机运行的、带会话沙箱的 Agent Skills 运行时**——用 LangGraph 编排「想 → 用工具 → 再看」的循环，用 Web 提供轻量对话界面，不追求做成 Open WebUI 或云端多租户产品。

## 核心原则

### 1. 会话即沙箱（Workspace-first）

每个 `(user_id, session_id)` 对应磁盘上独立目录：`data/`、`outputs/`、只读 `skills/` 链接。Agent 的 read/write/glob **只能碰这个目录**，不读用户整台电脑。上传文件进 `data/uploads/`，与工具路径一致，避免「界面说有、工具读不到」。

### 2. 图编排优先于 prompt 堆砌

行为由 **LangGraph 节点与边** 决定：何时注入系统提示、何时走 ToolNode、何时压缩上下文、何时结束。Prompt 负责原则与工具说明，**不**用超长 prompt 模拟路由。检查点（`var/state.db`）让多轮对话可恢复，无需客户端拼历史。

### 3. 工具一层、技能一层

- **MCP 工具**：稳定、可测试的原子能力（read、write、glob、call_skill、chroma_* 等），统一 schema 与 HTTP 发现。
- **Agent Skills**：`skills/*/SKILL.md` 说明书 + 可选脚本；通过 `call_skill` 按需加载正文，系统提示只带元数据 JSON。

扩展时优先「新 skill 目录」或「新 handler」，而不是在图里硬编码业务分支。

### 4. 薄 Web、厚服务端

Web 是 **Open WebUI 风格的薄客户端**：流式 SSE、会话列表、工作区面板、上传。不在浏览器里跑 Agent 逻辑。会话元数据在 `var/web/`，对话状态在 `var/state.db`，文件在 `var/workspace/`——职责分开，便于排查。

### 5. 本地优先、可渐进增强

默认单机：SQLite 检查点、本地 Chroma、`.env` 配 OpenAI 兼容 LLM/Embedding。Postgres、S3、独立 Chroma 服务在 compose 里可选，**不**挡本地跑通。Win/WSL/Mac 打开工作区目录是「本机开发体验」，不是远程 SaaS 能力。

### 6. 上下文要省，但不能「核爆」

长对话用 **软压缩（compact）**：保留 system + 当前轮工具链，旧消息收成一条 `[CONTEXT]`，而不是整段历史一刀切摘要。流式时单独 `status` 通道提示工具/压缩，不把过程噪音混进最终回复。

## 我们刻意不做的

| 不做 | 原因 |
|------|------|
| 完整 Open WebUI 克隆 | 范围失控；只做对话 + 工作区 + 多用户 |
| 浏览器端打开用户本机文件夹 | 安全与能力边界；打开资源管理器只在 **跑 uvicorn 的主机** |
| 无沙箱的全盘 read | 违背 Workspace-first |
| 把 MemPalace 当唯一记忆 | 同 session 靠检查点；向量记忆是跨 session 增强 |
| 过早 CLI/多租户/权限体系 | 等 Web + 工具链稳定再议 |

## 架构分层（对照代码）

```text
Web (web/)           → 展示、上传、会话列表
API (app/api/)       → HTTP / SSE
Runtime (app/runtime/) → LangGraph 图、节点、路由
MCP (app/mcp/)       → 工具注册与 LangChain 适配
Skills (skills/)     → 可扩展技能包
Workspace            → 每会话文件沙箱
MemPalace (可选)     → 跨会话语义召回
```

## 与「跟写指南」的关系

[agent_skills_build_guide.md](agent_skills_build_guide.md) 是**施工图纸**（M0→M15）；[milestones.md](milestones.md) 是**当前仓库已验收的进度表**。设计理念相对稳定；里程碑会随实现更新。

若你参与贡献：改功能时先想清楚动的是哪一层（Web / 图 / 工具 / skill），避免跨层耦合。
