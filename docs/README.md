# Caker 文档索引

| 文档 | 读者 | 内容 |
|------|------|------|
| [用户指南](user-guide.md) | 使用者 | Web 界面、工作区、上传、资源管理器、FAQ |
| [设计理念](design.md) | 产品 / 架构 | 是什么、原则、刻意不做 |
| [里程碑进度](milestones.md) | 开发者 | M0–M13 已实现路径与验收命令 |
| [Agent Skills 跟写指南](agent_skills_build_guide.md) | 实现者 | 分阶段从零搭仓库 |
| [基础知识手册](caker-base-knowledge.md) | 学习者 | LangGraph、工具、检查点 |
| [深度研究报告](user_attachments_session_a29c06ca28284858b68f5de84ede3306_outputs_agent_skills_deep_research_report.md) | 架构阅读 | 四层架构与节点 |
| [../README.md](../README.md) | 所有人 | 项目入口、快速开始 |
| [../AGENTS.md](../AGENTS.md) | AI 协作 | 改代码授权、checkpoint |
| [../system_prompt.md](../system_prompt.md) | 调 prompt | 注入模型的系统提示 |

## 维护约定

1. **用户操作** → 只改 `user-guide.md`（界面用语，少写 `app/` 路径）。
2. **理念与边界** → `design.md`；大功能方向变了先更新这里。
3. **验收与文件表** → `milestones.md`；每完成一个 M 追加一节。
4. **施工步骤** → `agent_skills_build_guide.md`；不与用户指南重复。
5. **根 README** → 保持简短：定位、快速开始、文档链接。

## 数据目录

| 路径 | 作用 |
|------|------|
| `var/workspace/<user>/<session>/` | 会话沙箱 |
| `var/web/` | Web 元数据 |
| `var/state.db` | 对话检查点 |
| `var/chroma/` | MemPalace（可选） |

默认 `WORKSPACE_ROOT=./var/workspace`（`.env`）。
