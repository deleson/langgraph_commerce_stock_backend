from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.market_data import (
    AdjustType,
    CandleTimeframe,
    MarketCode,
    MarketDataSource,
)
from app.schemas.strategy_signal import StrategySignalResponse
from app.services.market_data_quality_report_service import MarketDataQualityReportService
from app.services.strategy_signal_service import StrategySignalService
from app.services.technical_indicator_query_service import TechnicalIndicatorQueryService


class StrategySignalQueryService:
    """Build strategy signal responses from stored market candles.

    This service is an orchestration layer:
    1. load technical indicators from market_candles;
    2. load data quality report from market_candles;
    3. generate a strategy signal from both inputs.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        technical_indicator_query_service: TechnicalIndicatorQueryService | None = None,
        quality_report_service: MarketDataQualityReportService | None = None,
        strategy_signal_service: StrategySignalService | None = None,
    ) -> None:
        self.db = db
        self.technical_indicator_query_service = (
            technical_indicator_query_service
            or TechnicalIndicatorQueryService(db)
        )
        self.quality_report_service = (
            quality_report_service
            or MarketDataQualityReportService(db)
        )
        self.strategy_signal_service = strategy_signal_service or StrategySignalService()

    async def get_signal(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int = 120,
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
        include_detail: bool = True,
        min_required: int = 35,
        stale_after_days: int | None = None,
    ) -> StrategySignalResponse:
        normalized_symbol = symbol.strip().upper()

        technical_indicators = await self.technical_indicator_query_service.get_summary(
            symbol=normalized_symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
            adjust_type=adjust_type,
            source=source,
        )

        data_quality = await self.quality_report_service.get_quality_report(
            symbol=normalized_symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
            adjust_type=adjust_type,
            source=source,
            min_required=min_required,
            stale_after_days=stale_after_days,
        )

        return self.strategy_signal_service.generate_signal(
            technical_indicators=technical_indicators,
            data_quality=data_quality,
            include_detail=include_detail,
        )