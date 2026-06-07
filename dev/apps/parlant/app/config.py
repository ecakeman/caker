from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _load_policy(root: Path) -> None:
    path = root / "config" / "policy.env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class AppSettings:
    root: Path
    host: str
    port: int
    tool_service_port: int
    parlant_home: Path
    agent_name: str
    artifacts_root: Path
    llm_model: str
    llm_base_url: str
    llm_api_key: str
    embedding_model: str
    embedding_base_url: str
    embedding_api_key: str
    embedding_dimensions: int
    matching_top_k: int
    matching_rrf_k: int


def load_settings(root: Path | None = None) -> AppSettings:
    root = (root or Path(__file__).resolve().parents[1]).resolve()
    _load_policy(root)
    load_dotenv(root / ".env")

    def req(name: str) -> str:
        v = (os.environ.get(name) or "").strip()
        if not v:
            raise RuntimeError(f"Missing env: {name}")
        return v

    artifacts = Path((os.environ.get("ARTIFACTS_ROOT") or "artifacts").strip())
    if not artifacts.is_absolute():
        artifacts = (root / artifacts).resolve()

    return AppSettings(
        root=root,
        host=(os.environ.get("PARLANT_HOST") or "0.0.0.0").strip(),
        port=int((os.environ.get("PARLANT_PORT") or "8084").strip()),
        tool_service_port=int((os.environ.get("PARLANT_TOOL_SERVICE_PORT") or "9019").strip()),
        parlant_home=(root / (os.environ.get("PARLANT_HOME") or "var/runtime")).resolve(),
        agent_name=(os.environ.get("PARLANT_AGENT_NAME") or "卷叔").strip(),
        artifacts_root=artifacts,
        llm_model=req("LLM_MODEL_NAME"),
        llm_base_url=req("LLM_BASE_URL"),
        llm_api_key=req("LLM_API_KEY"),
        embedding_model=req("EMBEDDING_MODEL_NAME"),
        embedding_base_url=req("EMBEDDING_BASE_URL"),
        embedding_api_key=req("EMBEDDING_API_KEY"),
        embedding_dimensions=int((os.environ.get("EMBEDDING_DIMENSIONS") or "1024").strip()),
        matching_top_k=int((os.environ.get("MATCHING_TOP_K") or "5").strip()),
        matching_rrf_k=int((os.environ.get("MATCHING_RRF_K") or "60").strip()),
    )


def apply_runtime_env(settings: AppSettings) -> None:
    settings.parlant_home.mkdir(parents=True, exist_ok=True)
    os.environ["PARLANT_HOME"] = str(settings.parlant_home)
    os.environ["PARLANT_NLP"] = "litellm"
    os.environ["LLM_MODEL_NAME"] = settings.llm_model
    os.environ["LLM_BASE_URL"] = settings.llm_base_url
    os.environ["LLM_API_KEY"] = settings.llm_api_key
    os.environ["LITELLM_PROVIDER_MODEL_NAME"] = settings.llm_model
    os.environ["LITELLM_PROVIDER_BASE_URL"] = settings.llm_base_url
    os.environ["LITELLM_PROVIDER_API_KEY"] = settings.llm_api_key
    os.environ["EMBEDDING_MODEL_NAME"] = settings.embedding_model
    os.environ["EMBEDDING_BASE_URL"] = settings.embedding_base_url
    os.environ["EMBEDDING_API_KEY"] = settings.embedding_api_key
    os.environ["EMBEDDING_DIMENSIONS"] = str(settings.embedding_dimensions)
    os.environ["LITELLM_EMBEDDING_MODEL_NAME"] = settings.embedding_model
    os.environ["LITELLM_EMBEDDING_DIMENSIONS"] = str(settings.embedding_dimensions)
