from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.market_data import (
    AdjustType,
    CandleTimeframe,
    MarketCode,
    MarketDataSource,
)
from app.schemas.market_data_sync import MarketDataQualityReport
from app.schemas.strategy_signal import StrategySignalResponse
from app.schemas.technical_indicator import TechnicalIndicatorResponse
from app.services.market_data_quality_report_service import (
    MarketDataQualityReportService,
)
from app.services.strategy_signal_query_service import StrategySignalQueryService
from app.services.technical_indicator_query_service import (
    TechnicalIndicatorQueryService,
)


@dataclass(frozen=True)
class StockCandidateUniverseItem:
    symbol: str
    market: MarketCode
    name: str | None = None


@dataclass
class StockCandidateDataItem:
    symbol: str
    market: MarketCode
    name: str | None = None

    data_quality: MarketDataQualityReport | None = None
    technical_indicators: TechnicalIndicatorResponse | None = None
    strategy_signal: StrategySignalResponse | None = None

    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class StockCandidateDataService:
    """Load candidate stock data before scoring.

    This service does not score stocks.
    It only loads data needed by the later scoring service:
    - data quality report;
    - technical indicators;
    - strategy signal.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        quality_report_service: MarketDataQualityReportService | None = None,
        technical_indicator_query_service: TechnicalIndicatorQueryService | None = None,
        strategy_signal_query_service: StrategySignalQueryService | None = None,
    ) -> None:
        self.db = db
        self.quality_report_service = (
            quality_report_service
            or MarketDataQualityReportService(db)
        )
        self.technical_indicator_query_service = (
            technical_indicator_query_service
            or TechnicalIndicatorQueryService(db)
        )
        self.strategy_signal_query_service = (
            strategy_signal_query_service
            or StrategySignalQueryService(db)
        )

    async def get_data_for_candidates(
        self,
        *,
        candidates: list[StockCandidateUniverseItem],
        timeframe: CandleTimeframe = "1d",
        limit: int = 120,
        min_required_candles: int = 60,
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
        enforce_data_quality: bool = True,
        stale_after_days: int | None = None,
        include_strategy_signal: bool = True,
    ) -> list[StockCandidateDataItem]:
        results: list[StockCandidateDataItem] = []

        for candidate in candidates:
            result = await self._get_one_candidate_data(
                candidate=candidate,
                timeframe=timeframe,
                limit=limit,
                min_required_candles=min_required_candles,
                adjust_type=adjust_type,
                source=source,
                enforce_data_quality=enforce_data_quality,
                stale_after_days=stale_after_days,
                include_strategy_signal=include_strategy_signal,
            )
            results.append(result)

        return results

    async def _get_one_candidate_data(
        self,
        *,
        candidate: StockCandidateUniverseItem,
        timeframe: CandleTimeframe,
        limit: int,
        min_required_candles: int,
        adjust_type: AdjustType,
        source: MarketDataSource | None,
        enforce_data_quality: bool,
        stale_after_days: int | None,
        include_strategy_signal: bool,
    ) -> StockCandidateDataItem:
        symbol = self._normalize_symbol(candidate.symbol)
        market = candidate.market

        item = StockCandidateDataItem(
            symbol=symbol,
            market=market,
            name=candidate.name,
        )

        data_quality = await self.quality_report_service.get_quality_report(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
            adjust_type=adjust_type,
            source=source,
            min_required=min_required_candles,
            stale_after_days=stale_after_days,
        )
        item.data_quality = data_quality
        item.warnings.extend(data_quality.warnings)
        item.errors.extend(data_quality.errors)

        if self._should_skip_detail_loading(
            data_quality=data_quality,
            enforce_data_quality=enforce_data_quality,
        ):
            item.warnings.append(
                "候选股票数据质量未通过，已跳过技术指标和策略信号读取。"
            )
            return item

        try:
            item.technical_indicators = (
                await self.technical_indicator_query_service.get_summary(
                    symbol=symbol,
                    market=market,
                    timeframe=timeframe,
                    limit=limit,
                    adjust_type=adjust_type,
                    source=source,
                )
            )
        except Exception as exc:
            item.errors.append(f"failed to load technical indicators: {exc}")
            return item

        if not include_strategy_signal:
            return item

        try:
            item.strategy_signal = await self.strategy_signal_query_service.get_signal(
                symbol=symbol,
                market=market,
                timeframe=timeframe,
                limit=limit,
                adjust_type=adjust_type,
                source=source,
                include_detail=True,
                min_required=min_required_candles,
                stale_after_days=stale_after_days,
            )
        except Exception as exc:
            item.errors.append(f"failed to load strategy signal: {exc}")

        return item

    def _should_skip_detail_loading(
        self,
        *,
        data_quality: MarketDataQualityReport,
        enforce_data_quality: bool,
    ) -> bool:
        if data_quality.is_empty:
            return True

        if data_quality.errors:
            return True

        if not enforce_data_quality:
            return False

        return not data_quality.is_enough or data_quality.is_stale

    def _normalize_symbol(
        self,
        symbol: str,
    ) -> str:
        return symbol.strip().upper()