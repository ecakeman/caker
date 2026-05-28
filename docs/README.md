# Caker 文档索引

按**读者**选文档，避免在里程碑跟写指南里找「怎么用 Web」。

| 文档 | 读者 | 内容 |
|------|------|------|
| [用户指南](user-guide.md) | 使用者、验收、演示 | Web 界面、工作区、上传、多用户、资源管理器 |
| [README](../README.md) | 开发者 | 快速开始、里程碑进度、API 验证命令 |
| [Agent Skills 跟写指南](agent_skills_build_guide.md) | 实现者 | M0–M15 分阶段搭仓库 |
| [基础知识手册](caker-base-knowledge.md) | 学习者 | LangGraph、工具、检查点概念 |
| [深度研究报告](user_attachments_session_a29c06ca28284858b68f5de84ede3306_outputs_agent_skills_deep_research_report.md) | 架构阅读 | 四层架构与节点说明 |
| [AGENTS.md](../AGENTS.md) | AI 协作 | 改代码授权、checkpoint 约定 |
| [system_prompt.md](../system_prompt.md) | 调 prompt | 注入给模型的系统提示（非部署文档） |

## 建议写法（维护时）

1. **用户文档**（`user-guide.md`）：只写界面与操作，不写 `app/` 路径；用「工作区」「侧栏」等界面用语。
2. **README**：保留「如何跑起来 + 里程碑验收」；Web 一节链到用户指南，不重复长说明。
3. **跟写指南**：继续按里程碑增量写，不替代用户指南。
4. **概念/架构**：大段原理放基础知识或研究报告；README 只留一句话链接。
5. **变更时**：改功能 → 先改 `user-guide.md` 对应小节 → 再改 README 一句话 / Web 空状态（若面向用户）。

## 数据目录速查

| 路径 | 作用 |
|------|------|
| `var/workspace/<user>/<session>/` | 会话沙箱（`data/uploads/`、`outputs/`、`skills/` 链接） |
| `var/web/` | Web 用户列表、会话元数据、设置 |
| `var/state.db` | LangGraph 多轮检查点 |
| `var/chroma/` | MemPalace 向量（可选） |

默认 `WORKSPACE_ROOT=./var/workspace`（见 `.env`）。
