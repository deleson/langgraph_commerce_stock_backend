from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_candle import MarketCandle as MarketCandleModel
from app.models.market_symbol import MarketSymbol
from app.repositories.market_repo import AsyncMarketRepository
from app.schemas.market import (
    CandleTimeframe,
    MarketCandle,
    MarketCandleListResponse,
    MarketCode,
    MarketIndicatorResponse,
    MarketOverviewResponse,
    MarketQuoteResponse,
    MarketStockSearchItem,
)
from app.schemas.market_data import AdjustType, MarketCandleQuery, MarketDataSource
from app.schemas.stock_analysis import MarketSnapshot
from app.schemas.technical_indicator import TechnicalIndicatorResponse
from app.services.indicator_service import IndicatorService
from app.services.market_data_service import MockMarketDataService
from app.services.technical_indicator_query_service import TechnicalIndicatorQueryService


class MarketService:
    """Coordinate market data for API responses.

    Market API now reads PostgreSQL first and falls back to mock data.
    This keeps the public API stable while real providers are introduced.
    """

    def __init__(
        self,
        db: AsyncSession | None = None,
        market_data_service: MockMarketDataService | None = None,
        indicator_service: IndicatorService | None = None,
        repository: AsyncMarketRepository | None = None,
    ) -> None:
        self.db = db
        self.market_data_service = market_data_service or MockMarketDataService()
        self.indicator_service = indicator_service or IndicatorService()
        self.repository = repository or (AsyncMarketRepository(db) if db is not None else None)

    async def search_stocks(
        self,
        keyword: str | None = None,
        market: MarketCode | None = None,
    ) -> list[MarketStockSearchItem]:
        if self.repository is not None:
            db_symbols = await self.repository.list_symbols(
                market=market,
                keyword=keyword,
                active_only=True,
                limit=50,
            )

            if db_symbols:
                return [
                    self._build_search_item_from_model(symbol)
                    for symbol in db_symbols
                ]

        return self.market_data_service.search_stocks(
            keyword=keyword,
            market=market,
        )

    async def get_quote(
        self,
        symbol: str,
        market: MarketCode,
    ) -> MarketQuoteResponse:
        if self.repository is not None:
            db_quote = await self._get_quote_from_db(
                symbol=symbol,
                market=market,
            )
            if db_quote is not None:
                return db_quote

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
        if self.repository is not None:
            db_candles = await self._get_candles_from_db(
                symbol=symbol,
                market=market,
                timeframe=timeframe,
                limit=limit,
            )
            if db_candles is not None:
                return db_candles

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
        snapshot = await self._get_market_snapshot(
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
            source="db" if self.repository is not None else "mock",
        )

    async def get_overview(
        self,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int = 30,
        *,
        include_technical_indicators: bool = False,
        technical_indicator_limit: int = 120,
        adjust_type: AdjustType = "none",
        technical_indicator_source: MarketDataSource | None = None,
    ) -> MarketOverviewResponse:
        quote = await self.get_quote(symbol=symbol, market=market)
        indicators = await self.get_indicators(symbol=symbol, market=market)
        candles_response = await self.get_candles(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
        )

        technical_indicators = await self._get_technical_indicators_for_overview(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            include_technical_indicators=include_technical_indicators,
            technical_indicator_limit=technical_indicator_limit,
            adjust_type=adjust_type,
            technical_indicator_source=technical_indicator_source,
        )

        return MarketOverviewResponse(
            quote=quote,
            indicators=indicators,
            candles=candles_response.candles,
            technical_indicators=technical_indicators,
        )

    async def _get_quote_from_db(
        self,
        symbol: str,
        market: MarketCode,
    ) -> MarketQuoteResponse | None:
        if self.repository is None:
            return None

        normalized_symbol = symbol.strip().upper()

        market_symbol = await self.repository.get_symbol(
            symbol=normalized_symbol,
            market=market,
        )
        candles = await self.repository.list_candles(
            MarketCandleQuery(
                symbol=normalized_symbol,
                market=market,
                timeframe="1d",
                limit=2,
                adjust_type="none",
                source=None,
            )
        )

        if market_symbol is None or not candles:
            return None

        latest = candles[-1]
        previous = candles[-2] if len(candles) >= 2 else latest

        latest_price = self._decimal_to_float(latest.close_price)
        previous_close = self._decimal_to_float(previous.close_price)
        price_change = round(latest_price - previous_close, 4)
        price_change_percent = self._safe_percent(
            numerator=price_change,
            denominator=previous_close,
        )

        return MarketQuoteResponse(
            symbol=market_symbol.symbol,
            market=market_symbol.market,
            name=market_symbol.name,
            currency=market_symbol.currency,
            latest_price=latest_price,
            previous_close=previous_close,
            open_price=self._decimal_to_float(latest.open_price),
            high_price=self._decimal_to_float(latest.high_price),
            low_price=self._decimal_to_float(latest.low_price),
            volume=latest.volume,
            price_change=price_change,
            price_change_percent=price_change_percent,
            as_of=latest.candle_time,
            source=latest.source,
        )

    async def _get_candles_from_db(
        self,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe,
        limit: int,
    ) -> MarketCandleListResponse | None:
        if self.repository is None:
            return None

        normalized_symbol = symbol.strip().upper()

        candles = await self.repository.list_candles(
            MarketCandleQuery(
                symbol=normalized_symbol,
                market=market,
                timeframe=timeframe,
                limit=limit,
                adjust_type="none",
                source=None,
            )
        )

        if not candles:
            return None

        return MarketCandleListResponse(
            symbol=normalized_symbol,
            market=market,
            timeframe=timeframe,
            limit=len(candles),
            candles=[
                self._build_candle_response(candle)
                for candle in candles
            ],
            source=candles[-1].source,
        )

    async def _get_market_snapshot(
        self,
        symbol: str,
        market: MarketCode,
    ) -> MarketSnapshot:
        db_quote = await self._get_quote_from_db(
            symbol=symbol,
            market=market,
        )

        if db_quote is not None:
            return MarketSnapshot(
                symbol=db_quote.symbol,
                market=db_quote.market,
                name=db_quote.name,
                currency=db_quote.currency,
                latest_price=db_quote.latest_price,
                previous_close=db_quote.previous_close,
                open_price=db_quote.open_price,
                high_price=db_quote.high_price,
                low_price=db_quote.low_price,
                volume=db_quote.volume,
                as_of=db_quote.as_of,
            )

        return self.market_data_service.get_snapshot(
            symbol=symbol,
            market=market,
        )

    def _build_search_item_from_model(
        self,
        symbol: MarketSymbol,
    ) -> MarketStockSearchItem:
        return MarketStockSearchItem(
            symbol=symbol.symbol,
            market=symbol.market,
            name=symbol.name,
            currency=symbol.currency,
            exchange=symbol.exchange,
        )

    def _build_candle_response(
        self,
        candle: MarketCandleModel,
    ) -> MarketCandle:
        return MarketCandle(
            time=candle.candle_time,
            open_price=self._decimal_to_float(candle.open_price),
            high_price=self._decimal_to_float(candle.high_price),
            low_price=self._decimal_to_float(candle.low_price),
            close_price=self._decimal_to_float(candle.close_price),
            volume=candle.volume,
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

    def _decimal_to_float(
        self,
        value: Decimal,
    ) -> float:
        return float(value)

    def _safe_percent(
        self,
        numerator: float,
        denominator: float,
    ) -> float:
        if denominator == 0:
            return 0.0

        return round(numerator / denominator * 100, 4)

    async def _get_technical_indicators_for_overview(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe,
        include_technical_indicators: bool,
        technical_indicator_limit: int,
        adjust_type: AdjustType,
        technical_indicator_source: MarketDataSource | None,
    ) -> TechnicalIndicatorResponse | None:
        if not include_technical_indicators:
            return None

        if self.db is None:
            return None

        return await TechnicalIndicatorQueryService(self.db).get_summary(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            limit=technical_indicator_limit,
            adjust_type=adjust_type,
            source=technical_indicator_source,
        )