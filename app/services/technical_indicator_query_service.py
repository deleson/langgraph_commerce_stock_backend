from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.market_data import AdjustType, CandleTimeframe, MarketCode, MarketDataSource
from app.schemas.technical_indicator import (
    MacdSnapshot,
    MomentumSnapshot,
    MovingAverageSnapshot,
    RsiSnapshot,
    TechnicalIndicatorResponse,
    TechnicalIndicatorSummary,
    VolatilitySnapshot,
    VolumeFactorSnapshot,
)
from app.services.indicator_dataframe_service import IndicatorDataFrameService
from app.services.market_candle_series_service import MarketCandleSeriesService
from app.services.technical_indicator_service import TechnicalIndicatorService


class TechnicalIndicatorQueryService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        candle_series_service: MarketCandleSeriesService | None = None,
        dataframe_service: IndicatorDataFrameService | None = None,
        indicator_service: TechnicalIndicatorService | None = None,
    ) -> None:
        self.db = db
        self.candle_series_service = candle_series_service or MarketCandleSeriesService(db)
        self.dataframe_service = dataframe_service or IndicatorDataFrameService()
        self.indicator_service = indicator_service or TechnicalIndicatorService()

    async def get_moving_average(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int = 120,
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
    ) -> MovingAverageSnapshot:
        df = await self._get_dataframe(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
            adjust_type=adjust_type,
            source=source,
            min_required=5,
        )
        return self.indicator_service.calculate_moving_average(df)

    async def get_rsi(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int = 120,
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
    ) -> RsiSnapshot:
        df = await self._get_dataframe(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
            adjust_type=adjust_type,
            source=source,
            min_required=7,
        )
        return self.indicator_service.calculate_rsi(df)

    async def get_macd(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int = 120,
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
    ) -> MacdSnapshot:
        df = await self._get_dataframe(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
            adjust_type=adjust_type,
            source=source,
            min_required=35,
        )
        return self.indicator_service.calculate_macd(df)

    async def get_volatility(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int = 120,
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
    ) -> VolatilitySnapshot:
        df = await self._get_dataframe(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
            adjust_type=adjust_type,
            source=source,
            min_required=3,
        )
        return self.indicator_service.calculate_volatility(df)

    async def get_momentum(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int = 120,
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
    ) -> MomentumSnapshot:
        df = await self._get_dataframe(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
            adjust_type=adjust_type,
            source=source,
            min_required=6,
        )
        return self.indicator_service.calculate_momentum(df)

    async def get_volume_factor(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int = 120,
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
    ) -> VolumeFactorSnapshot:
        df = await self._get_dataframe(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
            adjust_type=adjust_type,
            source=source,
            min_required=5,
        )
        return self.indicator_service.calculate_volume_factor(df)

    async def get_summary(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe = "1d",
        limit: int = 120,
        adjust_type: AdjustType = "none",
        source: MarketDataSource | None = None,
    ) -> TechnicalIndicatorResponse:
        candles = await self.candle_series_service.get_candle_series(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
            adjust_type=adjust_type,
            source=source,
            min_required=35,
        )
        df = self.dataframe_service.candles_to_dataframe(candles)

        moving_average = self.indicator_service.calculate_moving_average(df)
        rsi = self.indicator_service.calculate_rsi(df)
        macd = self.indicator_service.calculate_macd(df)
        volatility = self.indicator_service.calculate_volatility(df)
        momentum = self.indicator_service.calculate_momentum(df)
        volume_factor = self.indicator_service.calculate_volume_factor(df)

        summary = TechnicalIndicatorSummary(
            moving_average=moving_average,
            rsi=rsi,
            macd=macd,
            volatility=volatility,
            momentum=momentum,
            volume_factor=volume_factor,
            interpretation=self._build_interpretation(
                moving_average=moving_average,
                rsi=rsi,
                macd=macd,
                volatility=volatility,
                momentum=momentum,
                volume_factor=volume_factor,
            ),
            warnings=self._build_warnings(),
        )

        latest_candle = candles[-1]

        return TechnicalIndicatorResponse(
            symbol=latest_candle.symbol,
            market=latest_candle.market,
            timeframe=latest_candle.timeframe,
            adjust_type=latest_candle.adjust_type,
            source=latest_candle.source,
            candle_count=len(candles),
            calculated_at=datetime.now(UTC),
            summary=summary,
        )

    async def _get_dataframe(
        self,
        *,
        symbol: str,
        market: MarketCode,
        timeframe: CandleTimeframe,
        limit: int,
        adjust_type: AdjustType,
        source: MarketDataSource | None,
        min_required: int,
    ):
        candles = await self.candle_series_service.get_candle_series(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
            adjust_type=adjust_type,
            source=source,
            min_required=min_required,
        )
        return self.dataframe_service.candles_to_dataframe(candles)

    def _build_interpretation(
        self,
        *,
        moving_average: MovingAverageSnapshot,
        rsi: RsiSnapshot,
        macd: MacdSnapshot,
        volatility: VolatilitySnapshot,
        momentum: MomentumSnapshot,
        volume_factor: VolumeFactorSnapshot,
    ) -> list[str]:
        return [
            f"均线趋势为 {moving_average.trend}。",
            f"RSI 状态为 {rsi.status}。",
            f"MACD 信号为 {macd.signal}。",
            f"波动率等级为 {volatility.level}。",
            f"动量方向为 {momentum.direction}。",
            f"成交量状态为 {volume_factor.status}。",
        ]

    def _build_warnings(
        self,
    ) -> list[str]:
        return [
            "技术指标基于历史 K 线计算，不代表未来一定走势。",
            "本结果仅用于学习和辅助分析，不构成投资建议。",
            "单一指标不应作为买入或卖出的唯一依据。",
        ]