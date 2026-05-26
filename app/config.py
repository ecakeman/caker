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

    workspace_root: str = Field(default="/tmp/skills")
    # 本地路线可留空；原 Pipeline/PG 持久化不在跟写范围
    pg_dsn: str = ""
    # 本地路线可留空；M10 用 SqliteSaver（var/state.db），不用 S3
    s3_endpoint: str = Field(default="http://localhost:9000")
    s3_bucket: str = Field(default="agent-skills-state")
    chroma_path: str = Field(default="./var/chroma")  # M15 MemPalace


settings = Settings()
