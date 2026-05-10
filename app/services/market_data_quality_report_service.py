from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.market_candle import MarketCandle
from app.schemas.market_data import (
    AdjustType,
    CandleTimeframe,
    MarketCandleCreate,
    MarketCode,
    MarketDataSource,
)
from app.schemas.market_data_sync import MarketDataQualityReport
from app.services.market_candle_series_service import MarketCandleSeriesService
from app.services.market_data_quality_service import MarketDataQualityService


class MarketDataQualityReportService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        candle_series_service: MarketCandleSeriesService | None = None,
        quality_service: MarketDataQualityService | None = None,
    ) -> None:
        self.db = db
        self.candle_series_service = candle_series_service or MarketCandleSeriesService(db)
        self.quality_service = quality_service or MarketDataQualityService()

    async def get_quality_report(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int = 120,
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
        min_required: int = 1,
        stale_after_days: int | None = None,
    ) -> MarketDataQualityReport:
        normalized_symbol = symbol.strip().upper()
        checked_at = datetime.now(UTC)

        try:
            candles = await self.candle_series_service.get_candle_series(
                symbol=normalized_symbol,
                market=market,
                timeframe=timeframe,
                limit=limit,
                adjust_type=adjust_type,
                source=source,
                min_required=1,
            )
        except NotFoundException:
            return MarketDataQualityReport(
                symbol=normalized_symbol,
                market=market,
                timeframe=timeframe,
                source=source,
                adjust_type=adjust_type,
                candle_count=0,
                duplicate_count=0,
                is_empty=True,
                is_enough=False,
                is_stale=False,
                errors=[f"market candles not found for {market}:{normalized_symbol}"],
                warnings=[],
                checked_at=checked_at,
            )

        candle_payloads = [
            self._to_candle_create(candle)
            for candle in candles
        ]

        quality_result = self.quality_service.inspect_candles(
            candle_payloads,
            min_required=min_required,
            stale_after_days=stale_after_days,
            now=checked_at,
        )

        return MarketDataQualityReport(
            symbol=normalized_symbol,
            market=market,
            timeframe=timeframe,
            source=source or self._infer_source(candles),
            adjust_type=adjust_type,
            candle_count=quality_result.candle_count,
            duplicate_count=quality_result.duplicate_count,
            earliest_candle_time=quality_result.earliest_candle_time,
            latest_candle_time=quality_result.latest_candle_time,
            is_empty=quality_result.is_empty,
            is_enough=quality_result.is_enough,
            is_stale=quality_result.is_stale,
            errors=quality_result.errors,
            warnings=quality_result.warnings,
            checked_at=checked_at,
        )

    def _to_candle_create(
        self,
        candle: MarketCandle,
    ) -> MarketCandleCreate:
        return MarketCandleCreate(
            symbol_id=candle.symbol_id,
            symbol=candle.symbol,
            market=candle.market,
            timeframe=candle.timeframe,
            candle_time=candle.candle_time,
            open_price=candle.open_price,
            high_price=candle.high_price,
            low_price=candle.low_price,
            close_price=candle.close_price,
            volume=candle.volume,
            amount=candle.amount,
            source=candle.source,
            is_adjusted=candle.is_adjusted,
            adjust_type=candle.adjust_type,
        )

    def _infer_source(
        self,
        candles: list[MarketCandle],
    ) -> str | None:
        if not candles:
            return None

        sources = {candle.source for candle in candles}

        if len(sources) == 1:
            return candles[0].source

        return "mixed"