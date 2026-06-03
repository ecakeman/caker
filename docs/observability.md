# 会话观测日志（Observability）

**引擎 JSONL 格式规范（v1.0）**：见 [engine_log_format_v1.md](./engine_log_format_v1.md)。

## 目录

每个会话工作区下的 `logs/`（Agent 只读，引擎写入）：

| 文件 | 来源 | 说明 |
|------|------|------|
| `engine.jsonl` | LangGraph / MCP | `tool_start`/`tool_end`、`llm_invoke`（含 token 用量）、`context_compact`、`mempalace_*`、`graph_error`、`sandbox_exec_done` |
| `sandbox.log` | exec 提议/执行 | 沙箱命令人类可读汇总（proposed / exec + stdout/stderr） |
| `sandbox.exec.jsonl` | `exec_pending` / `exec_runner` | `exec_proposed`、`exec_complete`（含 stdout_ref 大输出引用） |
| `sandbox.terminal.log` | Web PTY tee | 终端原始字节流（含 `[stdin]`） |
| `sandbox.terminal.txt` | 同上 | 剥离 ANSI，供 Agent `read` |
| `sandbox.container.log` | compose/venue `docker logs -f` | 容器 stdout/stderr |
| `sandbox.container.txt` | 同上 | 剥离 ANSI |
| `skills.jsonl` | `run_py_script` | 技能脚本 exit/stdout 摘要 |
| `agent.jsonl` | 可选 | `SESSION_AGENT_LOG_ENABLED=true` 时流式 delta / `llm_stream_end` |
| `blobs/*.txt` | 大参数/大输出 | 内容寻址；JSONL 中 `ref` / `result_ref` / `stdout_ref` 指向 |

## 配置（`.env`）

```env
SESSION_LOG_ENABLED=true              # 总开关，默认 true
SESSION_AGENT_LOG_ENABLED=false       # agent.jsonl，默认关
SESSION_LOG_MAX_BYTES=2097152         # 单文件轮转阈值（2MB）
SESSION_LOG_BLOB_THRESHOLD=1024       # 超过此字节数写入 logs/blobs/（v1 规范建议 1KB）
SESSION_LLM_PREVIEW_ENABLED=false     # 是否记录 prompt/completion 预览（默认关，注意隐私）
SESSION_LLM_PREVIEW_MAX_CHARS=1500    # 各 preview 字段上限
```

## JSONL 行格式

每行一个 JSON 对象，字段示例：

```json
{
  "ts": "2026-06-02T12:00:00.123Z",
  "source": "engine",
  "level": "INFO",
  "event": "llm_invoke",
  "msg": "completed",
  "meta": {
    "user_id": "local",
    "session_id": "abc",
    "run_id": "…",
    "prompt_tokens": 812,
    "completion_tokens": 143,
    "total_tokens": 955,
    "token_source": "provider",
    "prompt_preview": "…",
    "completion_preview": "…",
    "reasoning_preview": "…"
  }
}
```

大工具参数示例（`tool_start`）：

```json
{
  "event": "tool_start",
  "meta": {
    "args": {
      "path": "data/x.txt",
      "content": {
        "preview": "前 400 字…",
        "ref": "logs/blobs/a1b2c3d4e5f67890.txt",
        "len": 52000,
        "sha256": "…"
      }
    }
  }
}
```

`meta` 中 API key 等敏感字段会被脱敏；`prompt_tokens` / `completion_tokens` 等计数字段**不会**被误脱敏。

## Token 汇总

网关返回 usage 时，`llm_invoke` 含 `prompt_tokens`、`completion_tokens`；同轮多步 LLM 另有 `run_prompt_tokens` / `run_completion_tokens` 累计。

```bash
jq -s 'map(select(.event=="llm_invoke") | .meta.total_tokens // 0) | add' logs/engine.jsonl
```

无 usage 时不写 token 字段（与 tiktoken 的 `context_compact.token_estimate` 不同）。

## Agent 使用

- 排障：`read logs/engine.jsonl`、`read logs/sandbox.log`、`read logs/sandbox.exec.jsonl`
- 大工具参数/输出：`read logs/blobs/<hash>.txt`（由 JSONL 中 `ref` 给出路径）
- 终端失败：读 `logs/sandbox.terminal.txt` 尾部
- 容器服务日志：`read logs/sandbox.container.txt` 尾部
- **不可** `write logs/…`（ACL 拒绝，保证审计可信）

## 手工验收清单

- [ ] 文件树可见 `logs/`、`logs/blobs/`（有大输出时）
- [ ] 一轮带 `read` 的对话后 `engine.jsonl` 有 `tool_*`
- [ ] `write` 大文件后 `tool_start.meta.args` 含 `ref`，blob 可读
- [ ] 沙箱 propose → `sandbox.log` 有 `[proposed]`；approve 后 `[exec]` 与 stdout
- [ ] approve 后 `engine.jsonl` 有 `sandbox_exec_done`
- [ ] `llm_invoke` 含 token 字段（网关支持时）
- [ ] `SESSION_LLM_PREVIEW_ENABLED=true` 时可见 `prompt_preview` / `completion_preview`
- [ ] UI「日志」面板可见沙箱汇总 / Agent tab
- [ ] 助手气泡「复制」「重新生成」主站与沙箱均可用

## 相关代码

- [`docs/engine_log_format_v1.md`](./engine_log_format_v1.md) — 引擎 JSONL v1 规范
- [`app/observability/content_store.py`](../app/observability/content_store.py)
- [`app/observability/llm_meta.py`](../app/observability/llm_meta.py)
- [`app/web/regenerate.py`](../app/web/regenerate.py) — 重新生成 + checkpoint 同步
