"""Mock 行情 Provider 适配器。

它把 MockMarketDataService 生成的演示数据转换成 Provider 统一接口，
让行情同步链路在没有真实外部服务时也能完整运行。
"""

from decimal import Decimal

from app.core.exceptions import NotFoundException
from app.schemas.market_data import (
    CandleTimeframe,
    MarketCandleQuery,
    MarketCode,
    MarketProviderCandle,
    MarketSymbolCreate,
)
from app.services.market_data_service import MockMarketDataService
from app.services.market_providers.base import MarketDataProvider


class MockMarketDataProvider(MarketDataProvider):
    """开发、测试和降级场景使用的模拟 Provider。"""

    provider_name = "mock"

    def __init__(
        self,
        market_data_service: MockMarketDataService | None = None,
    ) -> None:
        self.market_data_service = market_data_service or MockMarketDataService()

    @property
    def supported_markets(self) -> set[MarketCode]:
        return {"US", "CN", "HK"}

    @property
    def supported_timeframes(self) -> set[CandleTimeframe]:
        return {"1d", "1h", "5m"}

    async def search_symbols(
        self,
        *,
        keyword: str | None = None,
        market: MarketCode | None = None,
        limit: int = 50,
    ) -> list[MarketSymbolCreate]:
        stocks = self.market_data_service.search_stocks(
            keyword=keyword,
            market=market,
        )

        return [
            self._to_symbol_create(stock)
            for stock in stocks[:limit]
        ]

    async def list_symbols(
        self,
        *,
        market: MarketCode | None = None,
        limit: int | None = None,
    ) -> list[MarketSymbolCreate]:
        stocks = self.market_data_service.search_stocks(
            keyword=None,
            market=market,
        )
        selected_stocks = stocks[:limit] if limit is not None else stocks
        return [self._to_symbol_create(stock) for stock in selected_stocks]

    async def get_symbol(
        self,
        *,
        symbol: str,
        market: MarketCode,
    ) -> MarketSymbolCreate:
        stocks = self.market_data_service.search_stocks(
            keyword=symbol,
            market=market,
        )

        normalized_symbol = symbol.strip().upper()

        for stock in stocks:
            if stock.symbol == normalized_symbol and stock.market == market:
                return self._to_symbol_create(stock)

        raise NotFoundException(
            message=f"mock symbol not found for {market}:{normalized_symbol}"
        )

    async def get_candles(
        self,
        query: MarketCandleQuery,
    ) -> list[MarketProviderCandle]:
        """把 Mock K 线转换成 MarketProviderCandle。"""

        candles = self.market_data_service.get_candles(
            symbol=query.symbol,
            market=query.market,
            timeframe=query.timeframe,
            limit=query.limit,
        )

        return [
            MarketProviderCandle(
                symbol=query.symbol,
                market=query.market,
                timeframe=query.timeframe,
                candle_time=candle.time,
                open_price=self._to_decimal(candle.open_price),
                high_price=self._to_decimal(candle.high_price),
                low_price=self._to_decimal(candle.low_price),
                close_price=self._to_decimal(candle.close_price),
                volume=candle.volume,
                amount=None,
                source="mock",
                is_adjusted=False,
                adjust_type=query.adjust_type,
            )
            for candle in candles
        ]

    def _to_symbol_create(
        self,
        stock,
    ) -> MarketSymbolCreate:
        return MarketSymbolCreate(
            symbol=stock.symbol,
            market=stock.market,
            name=stock.name,
            currency=stock.currency,
            exchange=stock.exchange,
            provider_symbol=stock.symbol,
            source="mock",
            is_active=True,
            raw_payload={
                "symbol": stock.symbol,
                "market": stock.market,
                "name": stock.name,
                "currency": stock.currency,
                "exchange": stock.exchange,
            },
        )

    def _to_decimal(
        self,
        value: float,
    ) -> Decimal:
        return Decimal(str(value))
