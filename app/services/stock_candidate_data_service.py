"""候选股票评分数据准备服务。

候选评分不是凭空打分：它需要先为每只候选股票收集数据质量报告、技术指标和策略
信号。本服务只负责加载这些上下文，不负责计算分数，也不调用 AI。
"""

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
    """候选股票池中的单个标的。"""

    symbol: str
    market: MarketCode
    name: str | None = None


@dataclass
class StockCandidateDataItem:
    """候选评分前的数据上下文。

    data_quality / technical_indicators / strategy_signal 是后续评分维度的输入；
    warnings / errors 用于记录单只股票读取过程中的问题。
    """

    symbol: str
    market: MarketCode
    name: str | None = None

    data_quality: MarketDataQualityReport | None = None
    technical_indicators: TechnicalIndicatorResponse | None = None
    strategy_signal: StrategySignalResponse | None = None

    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class StockCandidateDataService:
    """候选评分的数据加载层。

    它不直接给股票排名，只负责把评分所需材料准备好。
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
        """批量读取候选股票上下文。

        单只股票读取失败不会中断整个候选池，而是把错误写入该股票的 errors，
        让评分层决定是否排除。
        """

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
        """判断是否跳过技术指标和策略信号读取。

        数据为空或存在硬错误时必定跳过；如果 enforce_data_quality=True，
        数据不足或过旧也会跳过，避免后续评分建立在不可靠数据上。
        """

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
