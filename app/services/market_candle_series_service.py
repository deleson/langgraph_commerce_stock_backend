"""K 线序列读取服务。

技术指标、策略信号、回测等量化模块都需要按时间升序的一段 K 线。本服务把
“从数据库读取 K 线、校验最小样本数、按时间排序”收敛在一起，避免每个量化
Service 各自重复写查询和边界判断。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.market_candle import MarketCandle
from app.repositories.market_repo import AsyncMarketRepository
from app.schemas.market_data import (
    AdjustType,
    CandleTimeframe,
    MarketCandleQuery,
    MarketCode,
    MarketDataSource,
)


class MarketCandleSeriesService:
    """从 market_candles 表读取可用于量化计算的 K 线序列。"""

    def __init__(
        self,
        db: AsyncSession,
        *,
        repository: AsyncMarketRepository | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or AsyncMarketRepository(db)

    async def get_candle_series(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int = 120,
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
        min_required: int = 1,
    ) -> list[MarketCandle]:
        """读取指定股票的一段 K 线。

        source 和 adjust_type 会参与查询过滤，目的是防止 mock、tushare、前复权、
        不复权等不同口径的数据被混在一起计算。
        """

        normalized_symbol = symbol.strip().upper()

        if min_required <= 0:
            raise BadRequestException(message="min_required must be greater than 0")

        if limit < min_required:
            raise BadRequestException(message="limit must be greater than or equal to min_required")

        candles = await self.repository.list_candles(
            MarketCandleQuery(
                symbol=normalized_symbol,
                market=market,
                timeframe=timeframe,
                limit=limit,
                adjust_type=adjust_type,
                source=source,
            )
        )

        if not candles:
            raise NotFoundException(
                message=f"market candles not found for {market}:{normalized_symbol}"
            )

        if len(candles) < min_required:
            raise BadRequestException(
                message=(
                    f"not enough candles for {market}:{normalized_symbol}, "
                    f"required={min_required}, actual={len(candles)}"
                )
            )

        return self._sort_by_time(candles)

    def _sort_by_time(
        self,
        candles: list[MarketCandle],
    ) -> list[MarketCandle]:
        """统一按 candle_time 升序返回，保证 rolling / pct_change 等计算方向正确。"""

        return sorted(candles, key=lambda candle: candle.candle_time)
