"""行情 Provider 抽象接口。

Provider 是“外部行情源适配层”：BaoStock、Tushare、Mock 等不同来源的 API
形态都不一样，但进入项目后必须统一转换成项目自己的 Schema。这样 Service 层
只关心“拿到股票信息和 K 线”，不用知道每个供应商的字段名、日期格式或调用细节。
"""

from abc import ABC, abstractmethod

from app.schemas.market_data import (
    CandleTimeframe,
    MarketCandleQuery,
    MarketCode,
    MarketProviderCandle,
    MarketSymbolCreate,
)


class MarketDataProvider(ABC):
    """所有行情 Provider 必须实现的统一契约。

    新增真实行情源时，优先在这一层新增适配器，而不是把供应商 API 细节散落到
    MarketDataSyncService 或量化计算逻辑里。
    """

    provider_name: str

    @abstractmethod
    async def search_symbols(
        self,
        *,
        keyword: str | None = None,
        market: MarketCode | None = None,
        limit: int = 50,
    ) -> list[MarketSymbolCreate]:
        """从当前 Provider 搜索可交易标的。"""

    async def list_symbols(
        self,
        *,
        market: MarketCode | None = None,
        limit: int | None = None,
    ) -> list[MarketSymbolCreate]:
        """低频批量同步股票池。

        不是所有 Provider 都适合作为全量股票池来源，默认返回空列表。
        例如 BaoStock 当前只用于精确代码补齐和 K 线同步，避免错误地把它当成
        高频全市场搜索入口。
        """

        return []

    @abstractmethod
    async def get_symbol(
        self,
        *,
        symbol: str,
        market: MarketCode,
    ) -> MarketSymbolCreate:
        """读取单只股票的基础信息。"""

    @abstractmethod
    async def get_candles(
        self,
        query: MarketCandleQuery,
    ) -> list[MarketProviderCandle]:
        """读取历史 K 线，并返回尚未入库的 Provider 原始标准化结构。"""

    async def supports_market(
        self,
        market: MarketCode,
    ) -> bool:
        return market in self.supported_markets

    async def supports_timeframe(
        self,
        timeframe: CandleTimeframe,
    ) -> bool:
        return timeframe in self.supported_timeframes

    @property
    @abstractmethod
    def supported_markets(self) -> set[MarketCode]:
        """当前 Provider 支持的市场。"""

    @property
    @abstractmethod
    def supported_timeframes(self) -> set[CandleTimeframe]:
        """当前 Provider 支持的 K 线周期。"""
