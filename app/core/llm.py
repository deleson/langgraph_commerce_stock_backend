from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.core.exceptions import BadRequestException

@lru_cache
def get_chat_model() -> ChatOpenAI:
    settings = get_settings()

    if settings.llm_provider != "deepseek":
        raise BadRequestException(message="unsupported llm provider")

    if settings.deepseek_api_key is None:
        raise BadRequestException(message="missing DEEPSEEK_API_KEY")

    return ChatOpenAI(
        model = settings.llm_model,
        api_key = settings.deepseek_api_key.get_secret_value(),
        base_url = settings.llm_base_url,
        temperature = settings.llm_temperature,
    )