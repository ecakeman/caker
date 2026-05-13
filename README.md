# caker

在本地复现 [Agent Skills 跟写指南](docs/agent_skills_build_guide.md) 中的里程碑实现；架构说明见 [深度研究报告](docs/user_attachments_session_a29c06ca28284858b68f5de84ede3306_outputs_agent_skills_deep_research_report.md)。

## 当前进度（跟写）

- **M0**：FastAPI 入口、`GET /health`、配置与 Docker 依赖服务。
- **M1**：请按 `docs/agent_skills_build_guide.md` 的「M1 单轮 echo」自行新增/修改文件并验绿（本仓库不代写 M1 代码）。

## 快速开始（M0）

```bash
cd caker
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

另开终端：

```bash
curl -s http://127.0.0.1:8000/health
```

可选：启动 Postgres / MinIO / Chroma（Chroma 映射到本机 **8001**）：

```bash
docker compose up -d
```

## 文档依据

- 里程碑与验证命令：`docs/agent_skills_build_guide.md`
- 四层架构与图节点：`docs/user_attachments_session_a29c06ca28284858b68f5de84ede3306_outputs_agent_skills_deep_research_report.md`
