"""Redis 客户端管理。

Redis 在当前项目中承担缓存、Celery Broker 和 Celery Result Backend
等基础设施职责。生产环境中 Redis 只在 Docker 内网访问，不直接暴露公网端口。
"""

from functools import lru_cache

from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from app.core.config import get_settings


@lru_cache
def get_redis_client() -> Redis:
    """返回同步 Redis 客户端。

    使用缓存避免重复创建客户端对象，适合少量同步场景或兼容性代码使用。
    """

    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


@lru_cache
def get_async_redis_client() -> AsyncRedis:
    """返回异步 Redis 客户端。

    异步 API、Service 或缓存逻辑应优先使用该客户端，避免阻塞事件循环。
    """

    settings = get_settings()
    return AsyncRedis.from_url(settings.redis_url, decode_responses=True)
