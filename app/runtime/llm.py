from functools import lru_cache
from collections.abc import AsyncIterator, Sequence

from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

from app.config import settings


@lru_cache(maxsize=16)
def get_llm(model: str | None = None) -> BaseChatModel:
    key = settings.llm_api_key.strip()
    if not key:
        raise ValueError("请在 .env 中配置 LLM_API_KEY。")
    base = settings.llm_base_url.strip().rstrip("/")
    raw = (model or settings.llm_model_name).strip()
    if not raw:
        raise ValueError("请在 .env 中配置 LLM_MODEL_NAME。")
    name = settings.llm_model_name.strip()
    temperature = settings.llm_temperature
    return ChatOpenAI(
        model=name,
        api_key=key,
        base_url=base,
        temperature=temperature,
    )


def clear_llm_cache() -> None:
    get_llm.cache_clear()

async def stream_messages(messages: list[BaseMessage]) -> AsyncIterator[BaseMessage]:
    llm=get_llm()
    async for chunk in llm.astream(messages):
        yield chunk

def get_llm_with_tools(tools: Sequence[BaseTool]) -> Runnable:
    return get_llm().bind_tools(list(tools))