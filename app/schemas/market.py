from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from app.schemas.technical_indicator import TechnicalIndicatorResponse
from app.schemas.market_data_sync import (
    MarketDataQualityReport,
    MarketDataSyncStatusResponse,
)
from app.schemas.strategy_signal import StrategySignalResponse

MarketCode = Literal["US", "CN", "HK"]
CandleTimeframe = Literal["1d", "1h", "5m"]
TrendDirection = Literal["bullish", "bearish", "neutral"]
RiskLevel = Literal["low", "medium", "high"]


class MarketSymbolRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20, examples=["AAPL"])
    market: MarketCode = Field(examples=["US"])

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class MarketStockSearchItem(BaseModel):
    symbol: str
    market: MarketCode
    name: str
    currency: str
    exchange: str | None = None


class MarketQuoteResponse(BaseModel):
    symbol: str
    market: MarketCode
    name: str | None = None
    currency: str
    latest_price: float
    previous_close: float
    open_price: float
    high_price: float
    low_price: float
    volume: int
    price_change: float
    price_change_percent: float
    as_of: datetime
    source: str = "mock"


class MarketCandle(BaseModel):
    time: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: int


class MarketCandleListResponse(BaseModel):
    symbol: str
    market: MarketCode
    timeframe: CandleTimeframe
    limit: int
    candles: list[MarketCandle]
    source: str = "mock"


class MarketIndicatorResponse(BaseModel):
    symbol: str
    market: MarketCode
    price_change: float
    price_change_percent: float
    moving_average_5: float
    moving_average_20: float
    volatility_level: RiskLevel
    trend: TrendDirection
    source: str = "mock"


class MarketOverviewResponse(BaseModel):
    quote: MarketQuoteResponse
    indicators: MarketIndicatorResponse
    candles: list[MarketCandle] = Field(default_factory=list)
    technical_indicators: TechnicalIndicatorResponse | None = None
    data_quality: MarketDataQualityReport | None = None
    sync_status: MarketDataSyncStatusResponse | None = None
    strategy_signal: StrategySignalResponse | None = None