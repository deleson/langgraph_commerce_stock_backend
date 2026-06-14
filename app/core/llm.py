"""LLM 客户端工厂。

该文件根据配置创建聊天模型实例。生产环境当前使用 DeepSeek 的
OpenAI-compatible 接口；测试环境通常通过 mock 或 monkeypatch 避免真实调用。

注意：
这里只负责创建模型客户端；AI 额度检查、输出安全边界和 fallback
由业务 Service 或 LangGraph 节点负责。
"""

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.core.config import get_settings
from app.core.exceptions import BadRequestException

@lru_cache
def get_chat_model() -> ChatOpenAI:
    """返回配置好的聊天模型客户端。

    当前代码只支持 deepseek provider。缺少 DEEPSEEK_API_KEY 时主动抛出
    BadRequestException，避免在真实调用时才出现难定位的认证错误。
    """

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
