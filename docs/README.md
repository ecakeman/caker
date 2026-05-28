# 文档

本目录只保留当前仍在用的说明；项目介绍见仓库根目录 [README.md](../README.md)。

| 文档 | 适合 | 内容 |
|------|------|------|
| [user-guide.md](user-guide.md) | 使用者 | Web、工作区、上传、打开文件夹 |
| [milestones.md](milestones.md) | 开发者 | 已实现里程碑与验收 |
| [agent_skills_build_guide.md](agent_skills_build_guide.md) | 实现者 | 分阶段从零搭建引擎 |

仓库根目录还有：[AGENTS.md](../AGENTS.md)（协作约定）、[system_prompt.md](../system_prompt.md)（模型系统提示，非使用手册）。

## 写文档时放哪

- **介绍 / 功能 / 特点** → 根 `README.md`
- **怎么点界面** → `user-guide.md`
- **改了什么文件、怎么验** → `milestones.md`
- **跟写步骤与骨架** → `agent_skills_build_guide.md`

## 数据目录

| 路径 | 作用 |
|------|------|
| `var/workspace/<user>/<session>/` | 会话沙箱，`data/uploads/` 放上传 |
| `var/web/` | 用户、会话列表、Web 设置 |
| `var/state.db` | 多轮对话检查点 |
| `var/chroma/` | 跨会话语义记忆（可选） |

`WORKSPACE_ROOT` 默认 `./var/workspace`（`.env`）。
