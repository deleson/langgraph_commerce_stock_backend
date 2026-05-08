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
        return sorted(candles, key=lambda candle: candle.candle_time)