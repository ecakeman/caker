# Caker

## 项目介绍

Caker 是跑在本机的 **Agent Skills 助手**：浏览器里对话，Agent 在**当前会话工作区**里读文件、写结果、按技能执行任务。每个对话有独立目录（`user` + `session`），上传进 `data/uploads/`，工具只在该目录内读写，不碰你电脑上的其它路径。LangGraph 负责调度，自带 Web 聊天界面，数据落在本机 `var/`。

## 功能

- **对话**：多轮续聊，支持流式输出  
- **带文件问答**：网页上传 → Agent 用 `read` 等工具阅读、总结、改写  
- **工作区工具**：会话内读写信、搜索、编辑；产出写到 `outputs/`  
- **技能**：`skills/` 下按需加载说明与脚本（`call_skill`）  
- **工作区面板**：看已上传文件、复制路径、本机打开文件夹（Win+WSL / Mac / Linux）  
- **长对话**：上下文过长时自动压缩，减少超长报错  
- **记忆（可选）**：配置 Embedding 后可做跨会话语义召回  

## 特点

- **用户与会话分层** — 每 User 独占一套向量记忆（`user_id` 隔离，可选 MemPalace），下挂多个独立会话（各有工作区与聊天记录）；Web 侧栏切换用户、管理对话与工作区，无需手改配置  
- **会话即沙箱** — 上传路径与 Agent 工具路径一致，避免「侧栏有文件、模型读不到」  
- **图 + 工具 + 技能分层** — 流程在 LangGraph，原子能力在 MCP 工具，业务说明在 `skills/`  
- **薄 Web、厚服务端** — 浏览器只聊天和上传；Agent 与存储全在本机进程  
- **本地开箱** — 一条 `uvicorn` + `.env` 配 LLM 即可用，不绑特定云厂商  

---

## 快速开始

```bash
git clone https://github.com/ecakeman/caker.git
cd caker
cp .env.example .env   # 填写 LLM_*
pip install -e .
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

打开 **http://127.0.0.1:8000/** · 使用说明 [docs/user-guide.md](docs/user-guide.md)

---

## 文档

| 文档 | 说明 |
|------|------|
| [user-guide.md](docs/user-guide.md) | 界面与工作区 |
| [agent_skills_build_guide.md](docs/agent_skills_build_guide.md) | 跟写引擎 |
| [milestones.md](docs/milestones.md) | 里程碑验收 |
| [docs/README.md](docs/README.md) | 文档索引 |

开发：`pytest` / `scripts/validate_tools_skills.py` · 协作见 [AGENTS.md](AGENTS.md)
