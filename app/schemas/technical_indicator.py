"""技术指标响应 Schema。

本文件定义 MA、RSI、MACD、波动率、动量和成交量因子的输出结构。
指标公式计算在 Service 层完成，这里只负责把计算结果结构化返回。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.market_data import AdjustType, CandleTimeframe, MarketCode, MarketDataSource


TrendDirection = Literal["bullish", "bearish", "neutral"]
IndicatorStrength = Literal["weak", "normal", "strong"]
RiskLevel = Literal["low", "medium", "high"]
RsiStatus = Literal["oversold", "neutral", "overbought"]
MacdSignal = Literal["bullish", "bearish", "neutral"]
VolumeStatus = Literal["shrinking", "normal", "expanding"]


class MovingAverageSnapshot(BaseModel):
    """均线指标快照。"""

    ma5: float | None = Field(default=None, description="5-period simple moving average")
    ma10: float | None = Field(default=None, description="10-period simple moving average")
    ma20: float | None = Field(default=None, description="20-period simple moving average")
    ma60: float | None = Field(default=None, description="60-period simple moving average")
    ema12: float | None = Field(default=None, description="12-period exponential moving average")
    ema26: float | None = Field(default=None, description="26-period exponential moving average")
    trend: TrendDirection = Field(default="neutral", description="Trend inferred from moving averages")


class RsiSnapshot(BaseModel):
    """RSI 指标快照。"""

    rsi6: float | None = Field(default=None, ge=0, le=100, description="6-period RSI")
    rsi12: float | None = Field(default=None, ge=0, le=100, description="12-period RSI")
    rsi24: float | None = Field(default=None, ge=0, le=100, description="24-period RSI")
    status: RsiStatus = Field(default="neutral", description="RSI status")


class MacdSnapshot(BaseModel):
    """MACD 指标快照。"""

    dif: float | None = Field(default=None, description="MACD DIF line")
    dea: float | None = Field(default=None, description="MACD DEA signal line")
    histogram: float | None = Field(default=None, description="MACD histogram")
    signal: MacdSignal = Field(default="neutral", description="MACD directional signal")


class VolatilitySnapshot(BaseModel):
    """波动率指标快照。"""

    daily_return_std: float | None = Field(default=None, ge=0, description="Standard deviation of daily returns")
    annualized_volatility: float | None = Field(default=None, ge=0, description="Annualized volatility")
    level: RiskLevel = Field(default="low", description="Volatility risk level")


class MomentumSnapshot(BaseModel):
    """动量指标快照。"""

    momentum_5: float | None = Field(default=None, description="5-period price momentum")
    momentum_10: float | None = Field(default=None, description="10-period price momentum")
    momentum_20: float | None = Field(default=None, description="20-period price momentum")
    direction: TrendDirection = Field(default="neutral", description="Momentum direction")


class VolumeFactorSnapshot(BaseModel):
    """成交量因子快照。"""

    volume_ma5: float | None = Field(default=None, ge=0, description="5-period average volume")
    volume_ma20: float | None = Field(default=None, ge=0, description="20-period average volume")
    volume_ratio: float | None = Field(default=None, ge=0, description="Latest volume divided by volume_ma20")
    status: VolumeStatus = Field(default="normal", description="Volume expansion status")


class TechnicalIndicatorSummary(BaseModel):
    """技术指标汇总。"""

    moving_average: MovingAverageSnapshot
    rsi: RsiSnapshot
    macd: MacdSnapshot
    volatility: VolatilitySnapshot
    momentum: MomentumSnapshot
    volume_factor: VolumeFactorSnapshot
    interpretation: list[str] = Field(default_factory=list, description="Human-readable indicator interpretation")
    warnings: list[str] = Field(default_factory=list, description="Indicator limitations or risk warnings")


class TechnicalIndicatorResponse(BaseModel):
    """单只股票技术指标响应体。

    指标只基于历史 K 线计算，用于研究辅助，不构成投资建议。
    """

    symbol: str = Field(min_length=1, max_length=20)
    market: MarketCode
    timeframe: CandleTimeframe
    adjust_type: AdjustType = "none"
    source: MarketDataSource | str
    candle_count: int = Field(ge=0)
    calculated_at: datetime
    summary: TechnicalIndicatorSummary

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value
