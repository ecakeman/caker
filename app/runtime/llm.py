"""PAI-EAS / OpenAI 兼容网关：用 ChatOpenAI 调用。

与 clean_broker_gateway 一致：环境变量里可写 ``LLM_MODEL_NAME=openai/...``（LiteLLM 风格），
直连 OpenAI SDK / LangChain 发往 PAI-EAS 时需去掉 ``openai/`` 前缀，否则上游会报 model 不存在。
参见 clean_broker_gateway/scripts/customer_sim_20.py 中的 ``strip_provider_prefix``。
"""

from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

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
