from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _policy_path(root: Path) -> Path:
    return root / "config" / "policy.env"


def load_policy(root: Path) -> None:
    path = _policy_path(root)
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class PipelineSettings:
    root: Path
    raw_guidelines: Path
    raw_journeys: Path
    artifacts_root: Path
    embedding_model: str
    embedding_base_url: str
    embedding_api_key: str
    embedding_dimensions: int
    llm_model: str
    llm_base_url: str
    llm_api_key: str


def load_settings(root: Path | None = None) -> PipelineSettings:
    root = (root or Path(__file__).resolve().parents[1]).resolve()
    load_policy(root)
    load_dotenv(root / ".env")

    def req(name: str) -> str:
        v = (os.environ.get(name) or "").strip()
        if not v:
            raise RuntimeError(f"Missing env: {name}")
        return v

    def path_env(name: str, default: str) -> Path:
        raw = (os.environ.get(name) or default).strip()
        p = Path(raw)
        return p if p.is_absolute() else (root / p).resolve()

    return PipelineSettings(
        root=root,
        raw_guidelines=path_env("RAW_GUIDELINES_PATH", "data/raw/guidelines.json"),
        raw_journeys=path_env("RAW_JOURNEYS_PATH", "data/raw/journeys.json"),
        artifacts_root=path_env("ARTIFACTS_ROOT", "artifacts"),
        embedding_model=req("EMBEDDING_MODEL_NAME"),
        embedding_base_url=req("EMBEDDING_BASE_URL"),
        embedding_api_key=req("EMBEDDING_API_KEY"),
        embedding_dimensions=int((os.environ.get("EMBEDDING_DIMENSIONS") or "1024").strip()),
        llm_model=req("LLM_MODEL_NAME"),
        llm_base_url=req("LLM_BASE_URL"),
        llm_api_key=req("LLM_API_KEY"),
    )
