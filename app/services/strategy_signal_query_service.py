"""策略信号查询编排服务。

StrategySignalService 只负责规则评分；本服务负责从数据库读取技术指标和数据质量
报告，再把两者交给规则服务生成响应。API、Market Overview、候选评分和纸面交易
都可以复用这个入口。
"""

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
    """基于已入库 K 线生成策略信号。

    这里是编排层，不直接写公式，也不写数据库查询细节：
    1. TechnicalIndicatorQueryService 负责技术指标；
    2. MarketDataQualityReportService 负责数据质量；
    3. StrategySignalService 负责确定性评分。
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
        """生成单只股票策略信号。

        source / adjust_type 会同时传给技术指标和数据质量报告，保证两边使用同一批
        K 线口径，避免“指标来自 mock，质量报告来自 tushare”这种混用。
        """

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
