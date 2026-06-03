from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Qwen（阿里云百炼 / DashScope，OpenAI 兼容模式）
    # BASE_URL 说明：https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope
    llm_model_name: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    embedding_model_name: str = ""
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_dimensions: int = Field(default=1024, ge=1)

    @property
    def embedding_model(self) -> str:
        """DashScope 兼容模式模型名为 text-embedding-v4，非 openai/ 前缀。"""
        name = self.embedding_model_name.strip()
        if name.startswith("openai/"):
            return name.removeprefix("openai/")
        return name

    workspace_root: str = Field(default="./var/workspace")
    # 本地路线可留空；原 Pipeline/PG 持久化不在跟写范围
    pg_dsn: str = ""
    # 本地路线可留空；M10 用 SqliteSaver（var/state.db），不用 S3
    s3_endpoint: str = Field(default="http://localhost:9000")
    s3_bucket: str = Field(default="agent-skills-state")
    chroma_path: str = Field(default="./var/chroma")  # M15 MemPalace
    upload_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1)

    # Qwen3.5-397B-A17B 原生 262K；官方建议部署上下文至少 128K 以保留长程推理能力。
    # 压缩在 estimate_tokens >= max_input_tokens * compact_ratio 时触发（默认约 111K）。
    max_input_tokens: int = Field(default=131_072, ge=1000)
    compact_ratio: float = Field(default=0.85, ge=0.1, le=1.0)
    graph_recursion_limit: int = Field(default=50, ge=1)
    mempalace_auto_inject: bool = Field(default=False)
    # 上下文压缩触发后，将压缩要点写入 Chroma 长期记忆（需配置 EMBEDDING_*）
    mempalace_compact_persist: bool = Field(default=True)
    # 每轮对话结束后用 LLM 根据会话内容生成侧栏标题（替代首条消息截断）
    session_title_auto: bool = Field(default=True)
    user_profile_enabled: bool = Field(default=True)
    user_profile_max_entries: int = Field(default=50, ge=5)
    file_watch_poll_interval_default: float = Field(default=1.0, ge=0.5, le=60)
    daemon_max_per_session: int = Field(default=10, ge=1)
    # Read-only mirror of Caker source on GitHub (self-introspection; no workspace writes)
    caker_mirror_enabled: bool = Field(default=True)
    caker_mirror_repo: str = Field(default="ecakeman/caker")
    caker_mirror_ref: str = Field(default="main")
    caker_mirror_github_api: str = Field(default="https://api.github.com")
    caker_mirror_github_token: str = Field(default="", description="Optional; raises GitHub rate limits")
    caker_mirror_max_bytes: int = Field(default=512_000, ge=1024)
    caker_mirror_timeout_sec: int = Field(default=30, ge=5, le=120)
    caker_mirror_tree_cache_ttl_sec: int = Field(default=300, ge=30)
    session_log_enabled: bool = Field(default=True)
    session_agent_log_enabled: bool = Field(default=False)
    session_log_max_bytes: int = Field(default=2 * 1024 * 1024, ge=0)
    session_log_blob_threshold: int = Field(default=1024, ge=256)
    session_llm_preview_enabled: bool = Field(default=False)
    session_llm_preview_max_chars: int = Field(default=1500, ge=200)
    stream_emit_tool_status: bool = Field(default=True)

    # CEER V2 — Sandbox terminal + venue shell
    sandbox_terminal_enabled: bool = Field(default=True)
    sandbox_docker_bin: str = Field(default="docker")
    sandbox_venue_image: str = Field(default="python:3.12-slim")
    sandbox_venue_mount: str = Field(default="/workspace")
    docker_pull_mirror_prefix: str = Field(
        default="docker.m.daocloud.io",
        description="Empty to disable; prepended for venue image pull only",
    )


settings = Settings()
