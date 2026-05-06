from abc import ABC, abstractmethod

from app.schemas.market_data import (
    CandleTimeframe,
    MarketCandleQuery,
    MarketCode,
    MarketProviderCandle,
    MarketSymbolCreate,
)


class MarketDataProvider(ABC):
    """Base interface for all market data providers.

    Provider implementations hide vendor-specific API details and always return
    project-owned schemas. This keeps services independent from BaoStock,
    AKShare, Tushare, or any future paid data source.
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
        """Search tradable symbols from this provider."""

    @abstractmethod
    async def get_symbol(
        self,
        *,
        symbol: str,
        market: MarketCode,
    ) -> MarketSymbolCreate:
        """Get one symbol's basic information."""

    @abstractmethod
    async def get_candles(
        self,
        query: MarketCandleQuery,
    ) -> list[MarketProviderCandle]:
        """Get historical candles from this provider."""

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
        """Markets supported by this provider."""

    @property
    @abstractmethod
    def supported_timeframes(self) -> set[CandleTimeframe]:
        """Candle timeframes supported by this provider."""