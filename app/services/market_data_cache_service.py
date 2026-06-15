"""行情数据 Redis 缓存辅助服务。

当前项目以数据库为主存储，Redis 主要用于缓存高频读取结果和 Celery。这个服务
只定义缓存 key 规则和 JSON 读写方式，是否启用缓存由配置控制，业务 Service 可以
按需要逐步接入。
"""

import json
from typing import Any

from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.redis import get_async_redis_client
from app.schemas.market_data import AdjustType, CandleTimeframe, MarketCode, MarketDataSource


class MarketDataCacheService:
    """行情缓存读写与 key 构造工具。

    key 中会包含 market / symbol / timeframe / adjust_type / source 等口径字段，
    避免不同数据来源或不同复权方式的结果共用同一个缓存。
    """

    def __init__(
        self,
        redis: Redis | None = None,
    ) -> None:
        self.redis = redis or get_async_redis_client()
        self.settings = get_settings()

    async def get_json(
        self,
        key: str,
    ) -> dict[str, Any] | list[Any] | None:
        if not self.settings.market_data_cache_enabled:
            return None

        raw_value = await self.redis.get(key)

        if raw_value is None:
            return None

        return json.loads(raw_value)

    async def set_json(
        self,
        key: str,
        value: dict[str, Any] | list[Any],
        *,
        ttl_seconds: int,
    ) -> None:
        if not self.settings.market_data_cache_enabled:
            return

        await self.redis.set(
            key,
            json.dumps(value, ensure_ascii=False, default=str),
            ex=ttl_seconds,
        )

    async def delete(
        self,
        key: str,
    ) -> None:
        await self.redis.delete(key)

    def build_quote_key(
        self,
        *,
        symbol: str,
        market: MarketCode,
    ) -> str:
        return f"market:quote:{market}:{symbol.strip().upper()}"

    def build_candles_key(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe,
        limit: int,
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
    ) -> str:
        return (
            f"market:candles:{market}:{symbol.strip().upper()}:"
            f"{timeframe}:{limit}:{adjust_type}:{source or 'any'}"
        )

    def build_overview_key(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe,
        limit: int,
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
        include_technical_indicators: bool = False,
        include_data_quality: bool = False,
        include_sync_status: bool = False,
    ) -> str:
        return (
            f"market:overview:{market}:{symbol.strip().upper()}:"
            f"{timeframe}:{limit}:{adjust_type}:{source or 'any'}:"
            f"tech={int(include_technical_indicators)}:"
            f"quality={int(include_data_quality)}:"
            f"sync={int(include_sync_status)}"
        )

    def build_quality_report_key(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe,
        limit: int,
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
        min_required: int = 1,
        stale_after_days: int | None = None,
    ) -> str:
        return (
            f"market:quality:{market}:{symbol.strip().upper()}:"
            f"{timeframe}:{limit}:{adjust_type}:{source or 'any'}:"
            f"min={min_required}:stale={stale_after_days or 'none'}"
        )

    def build_sync_status_key(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe,
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
    ) -> str:
        return (
            f"market:sync-status:{market}:{symbol.strip().upper()}:"
            f"{timeframe}:{adjust_type}:{source or 'any'}"
        )

    def build_technical_summary_key(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe,
        limit: int,
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
    ) -> str:
        return (
            f"market:technical-summary:{market}:{symbol.strip().upper()}:"
            f"{timeframe}:{limit}:{adjust_type}:{source or 'any'}"
        )
