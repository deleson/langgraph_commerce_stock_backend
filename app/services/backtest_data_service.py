from dataclasses import dataclass
from datetime import UTC, datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.market_candle import MarketCandle
from app.repositories.market_repo import AsyncMarketRepository
from app.schemas.backtest import BacktestInputSnapshot, BacktestRequest


@dataclass(frozen=True)
class BacktestCandleData:
    candles: list[MarketCandle]
    input_snapshot: BacktestInputSnapshot
    warnings: list[str]


class BacktestDataService:
    """Load and validate market candles for backtests."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        repository: AsyncMarketRepository | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or AsyncMarketRepository(db)

    async def get_candles_for_backtest(
        self,
        request: BacktestRequest,
    ) -> BacktestCandleData:
        normalized_symbol = request.symbol.strip().upper()
        start_at = self._date_to_start_datetime(request.start_date)
        end_at = self._date_to_end_datetime(request.end_date)

        candles = await self.repository.list_candles_by_date_range(
            symbol=normalized_symbol,
            market=request.market,
            timeframe=request.timeframe,
            start_at=start_at,
            end_at=end_at,
            adjust_type=request.adjust_type,
            source=request.source,
        )

        if not candles:
            raise NotFoundException(
                message=(
                    "market candles not found for "
                    f"{request.market}:{normalized_symbol} "
                    f"from {request.start_date} to {request.end_date}"
                )
            )

        if len(candles) < request.min_required_candles:
            raise BadRequestException(
                message=(
                    "not enough candles for backtest, "
                    f"required={request.min_required_candles}, actual={len(candles)}"
                )
            )

        sorted_candles = self._sort_by_time(candles)

        return BacktestCandleData(
            candles=sorted_candles,
            input_snapshot=self._build_input_snapshot(
                request=request,
                candles=sorted_candles,
            ),
            warnings=self._build_warnings(
                request=request,
                candles=sorted_candles,
            ),
        )

    def _build_input_snapshot(
        self,
        *,
        request: BacktestRequest,
        candles: list[MarketCandle],
    ) -> BacktestInputSnapshot:
        first_candle = candles[0]
        last_candle = candles[-1]

        return BacktestInputSnapshot(
            candle_count=len(candles),
            first_candle_date=first_candle.candle_time.date(),
            last_candle_date=last_candle.candle_time.date(),
            strategy_name="strategy_signal_v1",
            timeframe=request.timeframe,
            adjust_type=request.adjust_type,
            source=request.source or last_candle.source,
            min_required_candles=request.min_required_candles,
            position_size_ratio=request.position_size_ratio,
            risk_control=request.risk_control,
        )

    def _build_warnings(
        self,
        *,
        request: BacktestRequest,
        candles: list[MarketCandle],
    ) -> list[str]:
        warnings: list[str] = []

        first_candle_date = candles[0].candle_time.date()
        last_candle_date = candles[-1].candle_time.date()

        if first_candle_date > request.start_date:
            warnings.append(
                "实际第一根 K 线晚于请求开始日期，回测将从可用数据开始。"
            )

        if last_candle_date < request.end_date:
            warnings.append(
                "实际最后一根 K 线早于请求结束日期，回测将以可用数据结束。"
            )

        if request.timeframe != "1d":
            warnings.append(
                "阶段六第一版主要面向日 K 回测，非日 K 结果需要谨慎解读。"
            )

        return warnings

    def _sort_by_time(
        self,
        candles: list[MarketCandle],
    ) -> list[MarketCandle]:
        return sorted(candles, key=lambda candle: candle.candle_time)

    def _date_to_start_datetime(
        self,
        value,
    ) -> datetime:
        return datetime.combine(value, time.min, tzinfo=UTC)

    def _date_to_end_datetime(
        self,
        value,
    ) -> datetime:
        return datetime.combine(value, time.max, tzinfo=UTC)