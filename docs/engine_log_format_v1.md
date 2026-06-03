# 引擎日志格式规范 (v1.0)

本文档定义了 Caker Runtime 引擎日志 (`logs/engine.jsonl`) 的标准格式。
所有日志条目必须为 **JSON Lines** 格式（每行一个合法的 JSON 对象）。

---

## 1. 通用字段结构

每个日志条目包含以下顶层字段：

| 字段名 | 类型 | 必填 | 说明 | 示例 |
| :--- | :--- | :--- | :--- | :--- |
| `ts` | String | ✅ | ISO 8601 时间戳 (UTC) | `"2026-06-03T03:05:19.277Z"` |
| `source` | String | ✅ | 日志来源模块 | `"engine"`, `"sandbox"`, `"skill"` |
| `level` | String | ✅ | 日志级别 | `"DEBUG"`, `"INFO"`, `"WARN"`, `"ERROR"` |
| `event` | String | ✅ | 事件类型 (见下文分类) | `"llm_invoke"`, `"tool_start"` |
| `msg` | String | ✅ | 事件简述/状态 | `"completed"`, `"glob"`, `"read"` |
| `meta` | Object | ✅ | 事件元数据 (结构依 event 而定) | `{...}` |

---

## 2. 事件类型与 Meta 结构

### 2.1 LLM 推理事件 (`llm_invoke`)

记录大模型调用详情。

**触发时机**: LLM 请求完成时。
**Msg 值**: `"completed"`

| Meta 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `user_id` | String | ✅ | 用户 ID |
| `session_id` | String | ✅ | 会话 ID |
| `run_id` | String | ✅ | 本次推理的唯一 ID |
| `elapsed_ms` | Integer | ✅ | 推理耗时 (毫秒) |
| `message_count` | Integer | ✅ | 当前上下文消息总数 |
| `model` | String | ⚠️ | 模型名称 (建议记录) | `"qwen3.5-397b-fp8"` |
| `prompt_tokens` | Integer | 🔲 | **输入 Token 数** (建议实现) |
| `completion_tokens` | Integer | 🔲 | **输出 Token 数** (建议实现) |
| `total_tokens` | Integer | 🔲 | **总 Token 数** (建议实现) |
| `cost_usd` | Float | 🔲 | **估算成本** (可选) |

**示例**:
```json
{
  "ts": "2026-06-03T03:46:51.877Z",
  "source": "engine",
  "level": "INFO",
  "event": "llm_invoke",
  "msg": "completed",
  "meta": {
    "user_id": "Sancho",
    "session_id": "chat-f680c563-d0ae-484c-a795-ebbfc7919e79",
    "run_id": "02f2c5a8-a56f-4612-bb44-736296d81ed9",
    "elapsed_ms": 10792,
    "message_count": 41,
    "model": "qwen3.5-397b-fp8",
    "prompt_tokens": 4520,
    "completion_tokens": 1250,
    "total_tokens": 5770,
    "cost_usd": 0.032
  }
}
```

---

### 2.2 工具调用开始 (`tool_start`)

记录工具调用的发起。

**触发时机**: 工具执行前。
**Msg 值**: 工具名称 (如 `"glob"`, `"read"`, `"sandbox_exec"`)

| Meta 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `user_id` | String | ✅ | 用户 ID |
| `session_id` | String | ✅ | 会话 ID |
| `run_id` | String | ✅ | 本次工具调用的唯一 ID |
| `args` | Object | ✅ | 工具参数快照 (敏感信息需脱敏) | `{"pattern": "logs/*"}` |

**示例**:
```json
{
  "ts": "2026-06-03T03:05:19.280Z",
  "source": "engine",
  "level": "INFO",
  "event": "tool_start",
  "msg": "glob",
  "meta": {
    "user_id": "Sancho",
    "session_id": "chat-f680c563-d0ae-484c-a795-ebbfc7919e79",
    "run_id": "cba43aeb-7b9a-4303-b7a6-0705655f616f",
    "args": {
      "pattern": "logs/**/*.log",
      "max_results": 100
    }
  }
}
```

---

### 2.3 工具调用结束 (`tool_end`)

记录工具调用的结果。

**触发时机**: 工具执行完成后。
**Msg 值**: 工具名称 (需与 `tool_start` 对应)

| Meta 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `user_id` | String | ✅ | 用户 ID |
| `session_id` | String | ✅ | 会话 ID |
| `run_id` | String | ✅ | 本次工具调用的唯一 ID (需与 start 对应) |
| `is_error` | Boolean | ✅ | 是否出错 |
| `preview` | String | ⚠️ | 结果预览 (截断至 200 字符) |
| `len` | Integer | 🔲 | 完整结果长度 (字节) |
| `sha256` | String | 🔲 | 完整结果哈希 (用于大文件引用) |
| `result_ref` | String | 🔲 | 大文件存储路径 (若结果过大) |
| `label` | String | 🔲 | 结果标签 (如 `"result"`) |

**示例 (成功)**:
```json
{
  "ts": "2026-06-03T03:05:19.281Z",
  "source": "engine",
  "level": "INFO",
  "event": "tool_end",
  "msg": "glob",
  "meta": {
    "user_id": "Sancho",
    "session_id": "chat-f680c563-d0ae-484c-a795-ebbfc7919e79",
    "run_id": "d157d1d9-7d77-4ccf-ab8a-7a4aa7237c39",
    "is_error": false,
    "preview": "{\"ok\": true, \"count\": 0, \"paths\": []}"
  }
}
```

**示例 (失败)**:
```json
{
  "ts": "2026-06-03T03:31:30.027Z",
  "source": "engine",
  "level": "ERROR",
  "event": "tool_end",
  "msg": "read",
  "meta": {
    "user_id": "Sancho",
    "session_id": "chat-f680c563-d0ae-484c-a795-ebbfc7919e79",
    "run_id": "ed6b2754-c794-402c-8b01-78243ebf72ba",
    "is_error": true,
    "preview": "{\"ok\": false, \"error\": \"not found: data/uploads/file.md\"}"
  }
}
```

**示例 (大文件读取)**:
```json
{
  "ts": "2026-06-03T03:44:27.232Z",
  "source": "engine",
  "level": "INFO",
  "event": "tool_end",
  "msg": "read",
  "meta": {
    "user_id": "Sancho",
    "session_id": "chat-f680c563-d0ae-484c-a795-ebbfc7919e79",
    "run_id": "bf3a0faa-cef2-4827-8650-b8a4e6bae152",
    "is_error": false,
    "preview": "1|{\"ts\": ...",
    "len": 10774,
    "sha256": "16890a6c5f72043415c82326297e0299074d4a7a76ab74655fbd072a4c15e7eb",
    "label": "result",
    "result_ref": "logs/blobs/16890a6c5f720434.txt"
  }
}
```

---

## 3. 最佳实践

1.  **时间同步**: 所有时间戳必须为 UTC，精度至少到毫秒。
2.  **Run ID 关联**: `tool_start` 和 `tool_end` 必须共享同一个 `run_id` 以便追踪链路。
3.  **敏感脱敏**: `args` 和 `preview` 中若包含 API Key、密码等，必须替换为 `***`。
4.  **大文件处理**: 若工具返回内容超过 1KB，不要直接写入 `preview`，应存入 `logs/blobs/` 并在日志中引用 `result_ref`。
5.  **Token 统计**: 强烈建议在 `llm_invoke` 中记录 `prompt_tokens` 和 `completion_tokens`，这是成本核算的核心依据。

---

## 4. 未来扩展预留

- **`skill_load`**: 记录技能脚本加载事件。
- **`context_compress`**: 记录上下文压缩事件（压缩比例、丢弃轮次）。
- **`memory_recall`**: 记录长期记忆召回事件（召回条数、相似度）。
- **`sandbox_stdout`**: 记录容器标准输出（可链接到 `sandbox.log`）。

---

*版本: 1.0 | 最后更新: 2026-06-03 | 作者: Caker Team*
