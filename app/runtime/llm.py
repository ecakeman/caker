from functools import lru_cache
from collections.abc import AsyncIterator, Sequence

from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

from app.tools.base import build_default_tools
from app.web.llm_settings import resolve_llm_credentials


@lru_cache(maxsize=32)
def get_llm(user_id: str | None = None, model: str | None = None) -> BaseChatModel:
    creds = resolve_llm_credentials(user_id)
    name = (model or creds.model).strip()
    return ChatOpenAI(
        model=name,
        api_key=creds.api_key,
        base_url=creds.base_url,
        temperature=creds.temperature,
        stream_usage=True,
    )


def clear_llm_cache() -> None:
    get_llm.cache_clear()


async def stream_messages(
    messages: list[BaseMessage],
    *,
    user_id: str | None = None,
) -> AsyncIterator[BaseMessage]:
    llm = get_llm(user_id)
    async for chunk in llm.astream(messages):
        yield chunk


def get_llm_with_tools(
    tools: Sequence[BaseTool],
    *,
    user_id: str | None = None,
    model: str | None = None,
) -> Runnable:
    return get_llm(user_id, model).bind_tools(list(tools))


def get_tools_for_state(*, streaming: bool) -> list[BaseTool]:
    return build_default_tools(include_result_set=not streaming)


def _configurable(config) -> dict:
    if config and isinstance(config, dict):
        raw = config.get("configurable") or {}
        if isinstance(raw, dict):
            return raw
    return {}


def user_id_from_config(config) -> str:
    return str(_configurable(config).get("user_id") or "local")


def session_id_from_config(config) -> str:
    cfg = _configurable(config)
    sid = cfg.get("session_id") or cfg.get("thread_id") or "demo"
    return str(sid).strip() or "demo"
