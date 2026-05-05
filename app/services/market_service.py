from app.schemas.market import (
    CandleTimeframe,
    MarketCandleListResponse,
    MarketCode,
    MarketIndicatorResponse,
    MarketOverviewResponse,
    MarketQuoteResponse,
    MarketStockSearchItem,
)
from app.schemas.stock_analysis import MarketSnapshot
from app.services.indicator_service import IndicatorService
from app.services.market_data_service import MockMarketDataService


class MarketService:
    """Coordinate market data for API responses.

    This service keeps routers thin and hides the current mock data source.
    Later, MockMarketDataService can be replaced by a real market data provider.
    """

    def __init__(
        self,
        market_data_service: MockMarketDataService | None = None,
        indicator_service: IndicatorService | None = None,
    ) -> None:
        self.market_data_service = market_data_service or MockMarketDataService()
        self.indicator_service = indicator_service or IndicatorService()

    async def search_stocks(
        self,
        keyword: str | None = None,
        market: MarketCode | None = None,
    ) -> list[MarketStockSearchItem]:
        return self.market_data_service.search_stocks(
            keyword=keyword,
            market=market,
        )

    async def get_quote(
        self,
        symbol: str,
        market: MarketCode,
    ) -> MarketQuoteResponse:
        snapshot = self.market_data_service.get_snapshot(
            symbol=symbol,
            market=market,
        )

        return self._build_quote_response(snapshot)

    async def get_candles(
        self,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int = 30,
    ) -> MarketCandleListResponse:
        candles = self.market_data_service.get_candles(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
        )

        normalized_symbol = symbol.strip().upper()

        return MarketCandleListResponse(
            symbol=normalized_symbol,
            market=market,
            timeframe=timeframe,
            limit=len(candles),
            candles=candles,
            source="mock",
        )

    async def get_indicators(
        self,
        symbol: str,
        market: MarketCode,
    ) -> MarketIndicatorResponse:
        snapshot = self.market_data_service.get_snapshot(
            symbol=symbol,
            market=market,
        )
        indicators = self.indicator_service.calculate(snapshot)

        return MarketIndicatorResponse(
            symbol=snapshot.symbol,
            market=snapshot.market,
            price_change=indicators.price_change,
            price_change_percent=indicators.price_change_percent,
            moving_average_5=indicators.moving_average_5,
            moving_average_20=indicators.moving_average_20,
            volatility_level=indicators.volatility_level,
            trend=indicators.trend,
            source="mock",
        )

    async def get_overview(
        self,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int = 30,
    ) -> MarketOverviewResponse:
        quote = await self.get_quote(symbol=symbol, market=market)
        indicators = await self.get_indicators(symbol=symbol, market=market)
        candles_response = await self.get_candles(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
        )

        return MarketOverviewResponse(
            quote=quote,
            indicators=indicators,
            candles=candles_response.candles,
        )

    def _build_quote_response(
        self,
        snapshot: MarketSnapshot,
    ) -> MarketQuoteResponse:
        price_change = round(
            snapshot.latest_price - snapshot.previous_close,
            4,
        )
        price_change_percent = self._safe_percent(
            numerator=price_change,
            denominator=snapshot.previous_close,
        )

        return MarketQuoteResponse(
            symbol=snapshot.symbol,
            market=snapshot.market,
            name=snapshot.name,
            currency=snapshot.currency,
            latest_price=snapshot.latest_price,
            previous_close=snapshot.previous_close,
            open_price=snapshot.open_price,
            high_price=snapshot.high_price,
            low_price=snapshot.low_price,
            volume=snapshot.volume,
            price_change=price_change,
            price_change_percent=price_change_percent,
            as_of=snapshot.as_of,
            source="mock",
        )

    def _safe_percent(
        self,
        numerator: float,
        denominator: float,
    ) -> float:
        if denominator == 0:
            return 0.0

        return round(numerator / denominator * 100, 4)