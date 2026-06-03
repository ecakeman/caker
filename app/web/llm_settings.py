from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings
from app.web_store.store import store


@dataclass(frozen=True)
class LlmCredentials:
    base_url: str
    api_key: str
    model: str
    temperature: float


def _default_connection() -> dict[str, str]:
    return {
        "id": "default",
        "name": "默认",
        "baseUrl": settings.llm_base_url.strip(),
        "apiKey": settings.llm_api_key.strip(),
    }


def get_user_llm_profile(user_id: str) -> dict[str, Any]:
    raw = store.load_settings()
    by_user = raw.get("llmByUser")
    if not isinstance(by_user, dict):
        by_user = {}
    profile = by_user.get(user_id)
    if not isinstance(profile, dict):
        profile = {}
    connections = profile.get("connections")
    if not isinstance(connections, list) or not connections:
        connections = [_default_connection()]
    return {
        "connections": connections,
        "activeConnectionId": profile.get("activeConnectionId") or connections[0].get("id", "default"),
        "activeModelId": profile.get("activeModelId") or settings.llm_model_name.strip(),
    }


def resolve_llm_credentials(user_id: str | None) -> LlmCredentials:
    uid = (user_id or "local").strip() or "local"
    profile = get_user_llm_profile(uid)
    conn_id = str(profile.get("activeConnectionId") or "default")
    connections = profile.get("connections") or []
    conn: dict[str, Any] | None = None
    for c in connections:
        if isinstance(c, dict) and str(c.get("id")) == conn_id:
            conn = c
            break
    if conn is None and connections and isinstance(connections[0], dict):
        conn = connections[0]

    base = (conn or {}).get("baseUrl") if conn else ""
    key = (conn or {}).get("apiKey") if conn else ""
    model = str(profile.get("activeModelId") or "").strip()

    base = str(base or settings.llm_base_url).strip().rstrip("/")
    key = str(key or settings.llm_api_key).strip()
    model = model or settings.llm_model_name.strip()

    if not key:
        raise ValueError("请配置 LLM API Key（设置页或 .env 的 LLM_API_KEY）。")
    if not model:
        raise ValueError("请选择或配置 LLM 模型（设置页或 .env 的 LLM_MODEL_NAME）。")

    return LlmCredentials(
        base_url=base,
        api_key=key,
        model=model,
        temperature=settings.llm_temperature,
    )


def _normalize_base_url(base_url: str) -> str:
    return base_url.strip().rstrip("/")


def resolve_api_key_for_models(
    user_id: str | None,
    *,
    base_url: str,
    api_key: str,
) -> str:
    """Use explicit key from the form, else stored profile/env key for the same base URL."""
    key = api_key.strip()
    if key:
        return key

    req_base = _normalize_base_url(base_url)
    if not req_base:
        raise ValueError("请填写 Base URL")

    uid = (user_id or "local").strip() or "local"
    profile = get_user_llm_profile(uid)
    for conn in profile.get("connections") or []:
        if not isinstance(conn, dict):
            continue
        conn_base = _normalize_base_url(str(conn.get("baseUrl") or ""))
        if conn_base == req_base:
            stored = str(conn.get("apiKey") or "").strip()
            if stored:
                return stored

    env_base = _normalize_base_url(settings.llm_base_url)
    if env_base and req_base == env_base:
        env_key = settings.llm_api_key.strip()
        if env_key:
            return env_key

    raise ValueError("请填写 API Key，或先保存设置后再刷新模型列表")


async def fetch_openai_models(*, base_url: str, api_key: str) -> list[dict[str, str]]:
    base = _normalize_base_url(base_url)
    key = api_key.strip()
    if not base:
        raise ValueError("baseUrl required")
    if not key:
        raise ValueError("apiKey required")
    url = f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"
    headers = {"Authorization": f"Bearer {key}"}
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise ValueError("API Key 无效或未授权，请检查设置") from e
            raise ValueError(f"上游返回 {e.response.status_code}: {e.response.text[:200]}") from e
        except httpx.HTTPError as e:
            raise ValueError(f"无法连接 LLM 网关: {e}") from e
        data = resp.json()
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    out: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        mid = item.get("id")
        if mid:
            out.append({"id": str(mid)})
    out.sort(key=lambda x: x["id"])
    return out
