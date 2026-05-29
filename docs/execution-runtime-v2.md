# CEER V2.1：沙箱工作台 + Agent 能力

Caker 本体在**宿主机**运行（`uvicorn`），不进 Docker。V2 提供 **执行环境工作台**（`sandbox.html`）：可拖拽三栏、文件树、CodeMirror 编辑器、Web 终端、与主站同款 Composer 对话；**compose 启停仅通过左下角按钮在宿主机执行**。

## 用户流程

1. 主站选择会话 → **进入执行环境**（确认）→ `sandbox.html`
2. 自备 `compose/docker-compose.yml` 后，点击左下角 **「启动环境」**（宿主机 `docker compose up -d`）
3. 若 compose 栈已 up，终端 `docker compose exec` 进入首个服务（优先名为 `dev`）
4. 否则附着 **venue 壳** 容器 `caker-venue-{user}-{session}`，挂载整个会话目录到 `/workspace`
5. **「停止环境」** 在宿主机 `compose down`；**退出工作台** 仅断开 WebSocket，不自动 down

## Agent 工具（V2.1）

| 工具 | 说明 |
|------|------|
| `read` / `write` / `edit` / `glob` | 工作区 `data/`、`outputs/`、`compose/`（路径自动规范化） |
| `sandbox_exec` | 提议容器内命令 → 沙箱 UI 弹窗确认 → `approve` 后执行 |
| `run_py_script` | 宿主机 `skills/**/scripts/*.py`（与容器分离） |

**统一 I/O 层**：MCP 工具与沙箱编辑器 HTTP API 共用 `app/workspace/paths.py`（路径规范化与 ACL）和 `app/workspace/io.py`（读写、512KB 上限）；Agent `write` 与编辑器 PUT 写入同一磁盘路径。

沙箱对话请求带 `x-sandbox: 1`，系统提示词注入 `[SANDBOX_CONTEXT]`（compose 是否 up、attach 目标）。

## 配置（`.env`）

| 变量 | 默认 | 说明 |
|------|------|------|
| `SANDBOX_TERMINAL_ENABLED` | `true` | 关闭后终端 WS 拒绝 |
| `SANDBOX_DOCKER_BIN` | `docker` | Docker CLI |
| `SANDBOX_VENUE_IMAGE` | `python:3.12-slim` | venue 壳镜像 |
| `DOCKER_PULL_MIRROR_PREFIX` | `docker.m.daocloud.io` | 仅 venue `pull` 时改写；空=直连 Hub |

用户自己在终端里的 `compose pull` 请配置本机 `daemon.json` 的 `registry-mirrors`。

## LLM 设置（主站）

- **设置**弹窗配置 OpenAI 兼容 **Base URL + API Key**，**刷新模型列表**（`GET /v1/models`）后选择模型
- 按侧栏 **用户** 存 `llmByUser`；沙箱右侧对话复用同一配置
- 空字段回退 `.env` 的 `LLM_*`

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| WS | `/api/v2/web/sessions/{id}/terminal?user_id=` | 终端 |
| GET | `/api/v2/web/sessions/{id}/workspace/tree` | 文件树 |
| GET/PUT | `/api/v2/web/sessions/{id}/workspace/file` | 编辑器读写 |
| GET | `/api/v2/web/sessions/{id}/compose/status` | compose 是否运行 |
| POST | `/api/v2/web/sessions/{id}/compose/up` | 宿主机启动 compose |
| POST | `/api/v2/web/sessions/{id}/compose/down` | 宿主机停止 compose |
| POST | `/api/v2/web/sessions/{id}/workspace/mkdir` | 新建文件夹 |
| POST | `/api/v2/web/sessions/{id}/workspace/copy` | 复制 |
| POST | `/api/v2/web/sessions/{id}/workspace/move` | 移动/重命名 |
| DELETE | `/api/v2/web/sessions/{id}/workspace/entry` | 删除 |
| GET | `/api/v2/web/sessions/{id}/exec/pending` | 待确认容器命令 |
| POST | `/api/v2/web/sessions/{id}/exec/approve` | 确认执行 |
| POST | `/api/v2/web/sessions/{id}/exec/reject` | 拒绝执行 |
| POST | `/api/v2/stream` | 流式对话（沙箱加 `x-sandbox: 1`） |
| GET/PUT | `/api/v2/web/llm/profile` | LLM 配置 |
| POST | `/api/v2/web/llm/models` | 代理列举模型 |

## 已移除（V1）

- `runtime.yaml` / `exec_*` MCP / `runtime/approve`
- 每轮对话销毁沙箱、镜像 allowlist
- Agent 直接读取 Web 终端输出

## 代码位置

- `app/execution/compose_control.py` — 宿主机 compose up/down
- `app/execution/docker_util.py` — Docker CLI、镜像前缀
- `app/execution/venue.py` — venue / compose exec 解析
- `app/execution/terminal.py` — WebSocket 会话
- `app/execution/exec_runner.py` — 一次性容器命令
- `app/execution/exec_pending.py` — 待确认队列
- `app/execution/sandbox_context.py` — 沙箱上下文注入
- `app/mcp/handlers/sandbox_exec.py` — Agent 提议执行
- `web/js/chat-ui.js` — 主站/沙箱共享对话 UI
- `web/js/composer-file-ref.js` — 拖放工作区路径到对话
- `web/js/workspace-context-menu.js` — 文件树右键菜单
- `system_prompt.md` — Agent 环境感知（引擎/工作区/执行环境）

## 手工验收清单

1. 打开沙箱 → 拖拽三栏 → 刷新布局保留
2. 点文件编辑 → 保存 → Agent `read` 同路径一致
3. Agent `write` `compose/docker-compose.yml` → 无路径错误 → 编辑器可打开
4. Agent `sandbox_exec` → 弹窗确认 → 自动续聊 → Agent 收到 exit/stdout 并继续作答
5. 左下角「启动环境」→ 终端 attach dev → 「停止环境」回 venue 壳
6. 文件树右键复制/重命名/删除；拖文件到对话框定位路径
7. 对话 Composer 与主站视觉一致（圆角 shell、停止/发送）
