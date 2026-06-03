# Caker 使用说明

面向在浏览器里使用 Caker 的人。项目概览见 [README](../README.md)；沙箱 API 与实现细节见 [execution-runtime-v2.md](execution-runtime-v2.md)。

---

## 目录

1. [安装与启动](#1-安装与启动)
2. [主站界面](#2-主站界面)
3. [用户、会话与身份](#3-用户会话与身份)
4. [LLM 设置](#4-llm-设置)
5. [对话与附件](#5-对话与附件)
6. [工作区与文件](#6-工作区与文件)
7. [执行环境工作台（沙箱）](#7-执行环境工作台沙箱)
8. [观测日志面板](#8-观测日志面板)
9. [Agent 能帮你做什么](#9-agent-能帮你做什么)
10. [数据存在哪里](#10-数据存在哪里)
11. [常见问题](#11-常见问题)

---

## 1. 安装与启动

### 1.1 准备

- Python **3.11+**
- 可访问的 **OpenAI 兼容** LLM 网关（见 [§4 LLM 设置](#4-llm-设置)）
- 使用沙箱终端 / 容器内命令时：本机安装 **Docker**

### 1.2 启动步骤

```bash
git clone https://github.com/ecakeman/caker.git
cd caker
cp .env.example .env
```

编辑 `.env`，至少配置：

```env
LLM_MODEL_NAME=你的模型名
LLM_BASE_URL=https://你的网关/v1
LLM_API_KEY=你的密钥
```

安装并运行：

```bash
pip install -e ".[dev]"
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

浏览器访问：**http://127.0.0.1:8000/**

顶栏状态点：**绿色** = `/health` 正常；**灰色** = 后端未就绪。

### 1.3 首次使用建议

1. 左下角确认 **User ID**（默认 `local`，可新建用户如 `Sancho`）
2. 顶栏 **设置** → 配置 LLM → **刷新模型列表** → 选模型 → 关闭设置（自动保存）
3. **新对话** → 上传或描述任务 → 发送

---

## 2. 主站界面

```
┌──────────────────┬─────────────────────────────────────┐
│ 侧栏             │ 顶栏：会话标题 · 日志 · 设置 · 状态点 │
│ · 新对话         ├─────────────────────────────────────┤
│ · 历史会话       │ 消息区（Markdown 渲染）               │
│ · 工作区面板     ├─────────────────────────────────────┤
│ · 用户列表       │ 输入框 · + 附件 · 发送 · 停止         │
│ · 进入执行环境   │                                     │
└──────────────────┴─────────────────────────────────────┘
```

| 元素 | 作用 |
|------|------|
| **新对话** | 新建 `session_id`，对应新的会话工作区目录 |
| **历史会话** | 切换对话；同一 session 内多轮上下文由服务端检查点恢复 |
| **工作区** | 当前会话上传文件列表、复制路径、打开本机文件夹 |
| **进入执行环境** | 打开 `sandbox.html`（IDE + 终端 + 同 thread 对话） |
| **日志** | 打开观测日志面板（`engine.jsonl`、沙箱日志等） |
| **设置** | 主题、LLM Base URL / API Key / 模型（按当前用户保存） |

流式输出默认开启；工具执行、上下文压缩时顶栏下方会出现**状态提示**（如「执行 read…」）。

---

## 3. 用户、会话与身份

### 用户（User ID）

- 侧栏左下 **用户列表** 切换；可 **添加用户**
- 影响：
  - 工作区路径：`var/workspace/<user_id>/...`
  - Web LLM 配置：`llmByUser.<user_id>`
  - 向量记忆范围（Chroma，按 user 隔离）
  - 跨会话 **用户偏好**（`user_profile`）

### 会话（Session）

- 每个对话一个 `session_id`（如 `chat-362d8e28-...`）
- 独立工作区目录与 LangGraph `thread_id`
- 删会话会清理对应 `var/web/sessions/` 元数据；工作区目录需通过管理流程删除

---

## 4. LLM 设置

### 4.1 打开设置

顶栏 **设置** → 配置后 **关闭弹窗** 即保存（无需单独点保存按钮）。

### 4.2 字段说明

| 字段 | 说明 |
|------|------|
| **连接名称** | 显示用，默认「默认」 |
| **Base URL** | OpenAI 兼容网关根地址，建议以 `/v1` 结尾 |
| **API Key** | 留空且此前已保存过 Key 时，**保留原 Key**；首次必须填写 |
| **模型** | 下拉列表；点 **刷新模型列表** 从网关 `GET /v1/models` 拉取 |

### 4.3 兼容的网关示例

Caker 使用 **OpenAI 兼容协议**（`ChatOpenAI`），不是 Anthropic Messages API。

| 提供商 | 推荐 Base URL | 说明 |
|--------|---------------|------|
| DeepSeek | `https://api.deepseek.com/v1` | 勿用 `/anthropic` 路径 |
| 阿里云百炼 / DashScope | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 见官方 OpenAI 兼容文档 |
| PAI-EAS 自部署 | `https://…/v1` | 你的 EAS 预测地址 + `/v1` |
| 本地 vLLM / LiteLLM | `http://127.0.0.1:8000/v1` | 需支持 chat/completions 与 models |

### 4.4 配置存哪里

| 来源 | 优先级 |
|------|--------|
| `var/web/settings.json` → `llmByUser.<user_id>` | **高**（设置页保存后） |
| `.env` 的 `LLM_*` | 该用户无 `llmByUser` 条目时的默认值 |

示例结构：

```json
{
  "llmByUser": {
    "Sancho": {
      "connections": [{
        "id": "default",
        "name": "默认",
        "baseUrl": "https://example.com/v1",
        "apiKey": "sk-..."
      }],
      "activeConnectionId": "default",
      "activeModelId": "qwen3.5-397b-fp8"
    }
  }
}
```

**安全提示**：API Key 明文存在本机 `settings.json`；`GET /llm/profile` 只返回 `hasApiKey`，不回显 Key。勿将 `var/web/` 提交到公开仓库。

### 4.5 刷新模型列表失败

- 确认 Base URL 可访问且为 **OpenAI 面**
- Key 未填时：若从未保存过 Key，需填一次并关闭设置；已保存则可留空再刷新
- 502/401：检查 Key、网络、网关是否提供 `/v1/models`

---

## 5. 对话与附件

### 5.1 发送消息

- 输入框支持 **Shift+Enter** 换行，**Enter** 发送
- 生成过程中可点 **停止**

### 5.2 上传附件

1. 输入框左侧 **+** 选择文件（有大小上限，默认 10MB）
2. 文件写入 `data/uploads/<文件名>`
3. 发送时附件路径会附在用户消息中；Agent 用 `read` / `glob` 读取

**注意**：切换会话会清空未发送的附件；若文件已被删除，发送前会提示重新上传。

### 5.3 多轮续聊

- 同一 session 内刷新页面或下次打开，历史由 `var/state.db` 检查点恢复
- 上下文过长时会自动 **压缩**较早对话（保留系统提示与当前轮工具链）

### 5.4 会话标题

默认在首轮对话结束后由 LLM 生成侧栏标题（可关：`SESSION_TITLE_AUTO=false`）。

---

## 6. 工作区与文件

### 6.1 目录结构

每个会话在磁盘上：

```text
var/workspace/<user_id>/<session_id>/
├── data/           # 上传、项目源码（可读写）
│   └── uploads/    # Web 上传默认位置
├── outputs/        # 分析报告、导出物（可读写）
├── compose/        # docker-compose.yml 等（可读写）
├── logs/           # 引擎/沙箱观测日志（Agent 只读）
├── skills/         → 仓库 skills/ 符号链接（只读）
└── books/          # 可选只读资料（若存在）
```

### 6.2 侧栏工作区面板

| 操作 | 说明 |
|------|------|
| **复制路径** | Win+WSL 优先复制 `\\wsl.localhost\...` |
| **打开资源管理器** | 在 **运行 uvicorn 的机器** 上打开文件夹 |
| **文件列表** | 当前会话 `data/uploads` 等摘要 |

### 6.3 Agent 改文件

默认 Agent 会先说明拟改路径并等你同意；若你明确说「直接改」「写进文件」，视为已授权。

---

## 7. 执行环境工作台（沙箱）

从主站 **进入执行环境** 打开 `sandbox.html`，与主站 **同一会话、同一对话 thread**。

### 7.1 布局

- **左**：文件树（与工作区同一目录）
- **中**：CodeMirror 编辑器
- **下**：Web 终端（Docker 内 Shell）
- **右**：对话（请求带 `x-sandbox: 1`，注入沙箱上下文）

### 7.2 典型流程

1. 在主站或沙箱里让 Agent 写好 `compose/docker-compose.yml`（位于 `compose/`）
2. 沙箱左下角 **启动环境** → 宿主机 `docker compose up -d`
3. 终端自动 attach 到 compose 服务（优先服务名 `dev`）或 **venue 壳** 容器
4. 在终端里 `pip install` / `pytest` / 跑服务；或在对话里让 Agent 使用 `sandbox_exec`（需你在 UI **确认**后执行）
5. **停止环境** → compose down；**退出工作台** 只断 WebSocket，不自动 down

### 7.3 无 compose 时

未配置 compose 时，终端进入 `caker-venue-{user}-{session}`，会话目录挂载为容器内 `/workspace`（镜像默认 `python:3.12-slim`）。

### 7.4 Agent 在容器内跑命令

- **`sandbox_exec`**：Agent 提议命令 → 沙箱 UI 弹窗 → 你确认后执行（有超时，适合短命令）
- **`daemon_start`**：后台长任务（训练、批处理）；用 `daemon_attach` 或读 `logs/daemons/<name>.log` 看进度

终端输出会 tee 到 `logs/sandbox.terminal.txt` 等；Agent 可读这些日志，**不能**直接看到你的实时终端画面。

---

## 8. 观测日志面板

主站或沙箱顶栏 **日志** 打开面板，轮询当前会话 `logs/` 下文件。

| Tab / 文件 | 内容 |
|------------|------|
| **Engine** | `engine.jsonl`：工具调用、LLM token、压缩、错误 |
| **Sandbox** | `sandbox.log`、`sandbox.exec.jsonl` |
| **Agent** | `agent.jsonl`（需 `SESSION_AGENT_LOG_ENABLED=true`） |
| **Terminal / Container** | 剥离 ANSI 的终端与容器输出 |

Agent 也可 `read logs/engine.jsonl`（建议 `offset=-50` 读尾部）。大内容见 `logs/blobs/` 与 JSONL 中的 `ref` 字段。

详见 [observability.md](observability.md)。

---

## 9. Agent 能帮你做什么

### 9.1 工具概览（用户视角）

| 类别 | 典型用途 |
|------|----------|
| 工作区 I/O | 读写信、搜索、编辑、HTTP 下载到 `data/` |
| 技能 | 加载 `skills/` 下 SKILL.md，按步骤执行 |
| 宿主机脚本 | `run_py_script` 跑 `skills/*/scripts/*.py` |
| 容器执行 | `sandbox_exec`（需确认）、`daemon_*`（后台） |
| 文件盯梢 | `watch_start` → 事件在 `logs/watch_events.jsonl` |
| 记忆 | `chroma_in` / `chroma_out`；「记住这个」类需求 |
| Caker 自省 | `caker_mirror_read` 读 [GitHub 上的 Caker 源码](https://github.com/ecakeman/caker)（只读） |

### 9.2 用户偏好

对话结束后，引擎可能自动提炼你的习惯（如输出格式、工具偏好），写入跨会话 `user_profile`，下次对话默认遵守。

### 9.3 限制（需有预期）

- Agent **不能**改 Caker 引擎本体代码（只能读 GitHub 镜子）
- **不能**代替你在未确认时执行 `sandbox_exec`
- **不能**读写其他 user/session 的工作区
- 沙箱终端里请用工作台按钮启停 compose，不要依赖 Agent 替你 `docker compose up`

---

## 10. 数据存在哪里

| 内容 | 路径 | 说明 |
|------|------|------|
| Web 设置、LLM | `var/web/settings.json` | 主题、当前用户、每用户 LLM |
| 用户列表 | `var/web/users.json` | |
| 会话列表元数据 | `var/web/sessions/<user>/<id>.json` | 标题、更新时间 |
| 聊天消息（检查点） | `var/state.db` | 同 session 续聊 |
| 文件与产出 | `var/workspace/<user>/<session>/` | |
| 向量记忆 | `var/chroma/` | 需配置 Embedding |
| 用户偏好 | `var/workspace/<user>/profile/user_profile.jsonl` | 跨 session |

换浏览器只要连**同一后端**，设置与会话列表仍在；清浏览器缓存不影响服务端数据。

---

## 11. 常见问题

**Q：设置里刷新模型 502 / 401**  
A：检查 Base URL 是否为 OpenAI 兼容面、Key 是否正确；首次需填 Key 并关闭设置保存；DeepSeek 请用 `https://api.deepseek.com/v1`，不要用 `/anthropic`。

**Q：侧栏工作区「失败」**  
A：重启 uvicorn，浏览器 **Ctrl+Shift+R** 硬刷新。

**Q：Agent 说找不到文件，侧栏却有**  
A：确认当前会话与上传时一致；检查路径是否为 `data/uploads/...`。

**Q：打开文件夹没反应**  
A：「打开资源管理器」只在 **跑 uvicorn 的那台机器** 生效；纯 SSH 服务器请用「复制路径」。

**Q：沙箱终端连不上**  
A：确认 Docker 运行中；WSL2 需在 Linux 内启动服务；看 `SANDBOX_TERMINAL_ENABLED` 是否为 true。

**Q：对话突然变短 / 提到「压缩」**  
A：上下文接近上限时的正常行为；要点可能写入 `[CONTEXT]` 或 Chroma（若开启）。

**Q：如何备份**  
A：复制整个 `var/` 目录（含 `workspace`、`web`、`state.db`、`chroma`）。

---

## 相关文档

- [文档索引](README.md)
- [执行环境技术说明](execution-runtime-v2.md)
- [观测日志](observability.md)
- [里程碑验收](milestones.md)（开发者）
