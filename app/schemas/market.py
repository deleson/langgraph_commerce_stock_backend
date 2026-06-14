"""行情查询 API 使用的响应 Schema。

本文件面向前端/API 返回轻量行情、K 线列表、基础指标和聚合概览。
真实行情来源、缓存、同步和数据质量判断由 Service 层完成。
"""

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
    """单只股票行情请求参数。"""

    symbol: str = Field(min_length=1, max_length=20, examples=["AAPL"])
    market: MarketCode = Field(examples=["US"])

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class MarketStockSearchItem(BaseModel):
    """股票搜索结果项。"""

    symbol: str
    market: MarketCode
    name: str
    currency: str
    exchange: str | None = None


class MarketQuoteResponse(BaseModel):
    """实时或准实时行情快照响应。"""

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
    """API 返回的单根 K 线。"""

    time: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: int


class MarketCandleListResponse(BaseModel):
    """K 线列表响应。"""

    symbol: str
    market: MarketCode
    timeframe: CandleTimeframe
    limit: int
    candles: list[MarketCandle]
    source: str = "mock"


class MarketIndicatorResponse(BaseModel):
    """兼容早期接口的基础指标响应。"""

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
    """行情聚合概览响应。

    overview 会把 quote、K 线、数据质量、技术指标和策略信号聚合到同一响应中，
    便于主分析图、候选评分和前端详情页复用。
    """

    quote: MarketQuoteResponse
    indicators: MarketIndicatorResponse
    candles: list[MarketCandle] = Field(default_factory=list)
    technical_indicators: TechnicalIndicatorResponse | None = None
    data_quality: MarketDataQualityReport | None = None
    sync_status: MarketDataSyncStatusResponse | None = None
    strategy_signal: StrategySignalResponse | None = None
