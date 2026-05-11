from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.market_data_sync import MarketDataQualityReport
from app.schemas.technical_indicator import TechnicalIndicatorResponse


MarketCode = Literal["US", "CN", "HK"]
AnalysisType = Literal["stock_basic"]
TrendDirection = Literal["bullish", "bearish", "neutral"]
RiskLevel = Literal["low", "medium", "high"]
GraphRoute = Literal["normal", "degraded", "unavailable", "error"]


class StockAnalysisRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20, examples=["AAPL"])
    market: MarketCode = Field(examples=["US"])
    analysis_type: AnalysisType = Field(default="stock_basic")
    thread_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Optional analysis conversation id. If omitted, service will generate one.",
    )

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("thread_id", mode="before")
    @classmethod
    def normalize_thread_id(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value


class MarketSnapshot(BaseModel):
    symbol: str
    market: MarketCode
    name: str | None = None
    currency: str = "USD"
    latest_price: float
    previous_close: float
    open_price: float
    high_price: float
    low_price: float
    volume: int
    as_of: datetime


class IndicatorSnapshot(BaseModel):
    price_change: float
    price_change_percent: float
    moving_average_5: float
    moving_average_20: float
    volatility_level: RiskLevel
    trend: TrendDirection


class StockAnalysisResult(BaseModel):
    summary: str
    risk_level: RiskLevel
    trend: TrendDirection
    key_points: list[str] = Field(default_factory=list)
    suggestion: str
    warnings: list[str] = Field(default_factory=list)


class StockAnalysisQualityContext(BaseModel):
    data_quality: MarketDataQualityReport | None = None
    graph_route: GraphRoute | None = None
    route_reason: str | None = Field(default=None, max_length=500)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class StockAnalysisContextSnapshot(BaseModel):
    thread_id: str
    user_id: int
    symbol: str
    market: MarketCode
    analysis_type: AnalysisType = "stock_basic"
    risk_preference: Literal["conservative", "balanced", "aggressive"] = "balanced"
    graph_route: GraphRoute | None = None
    quality_context: StockAnalysisQualityContext | None = None
    market_snapshot: MarketSnapshot | None = None
    indicators: IndicatorSnapshot | None = None
    technical_indicators: TechnicalIndicatorResponse | None = None
    result: StockAnalysisResult | None = None
    record_id: int | None = None
    notification_id: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class StockAnalysisResponse(BaseModel):
    record_id: int | None = None
    thread_id: str | None = None
    symbol: str
    market: MarketCode
    analysis_type: AnalysisType
    status: Literal["completed", "failed"]
    graph_route: GraphRoute | None = None
    quality_context: StockAnalysisQualityContext | None = None
    market_snapshot: MarketSnapshot
    indicators: IndicatorSnapshot
    result: StockAnalysisResult
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class StockAnalysisFollowUpRequest(BaseModel):
    thread_id: str = Field(
        min_length=1,
        max_length=100,
        description="Analysis conversation id returned by stock analysis API.",
    )
    message: str = Field(
        min_length=1,
        max_length=1000,
        description="User follow-up question about a previous stock analysis.",
    )

    @field_validator("thread_id", "message", mode="before")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value


class StockAnalysisFollowUpResponse(BaseModel):
    thread_id: str
    answer: str
    referenced_analysis_record_id: int | None = None
    referenced_symbol: str | None = None
    referenced_market: MarketCode | None = None
    created_at: datetime | None = None


class StockAnalysisGraphState(BaseModel):
    user_id: int
    symbol: str
    market: MarketCode
    analysis_type: AnalysisType = "stock_basic"
    thread_id: str | None = None
    risk_preference: Literal["conservative", "balanced", "aggressive"] = "balanced"
    graph_route: GraphRoute | None = None
    quality_context: StockAnalysisQualityContext | None = None
    context_snapshot: StockAnalysisContextSnapshot | None = None
    market_snapshot: MarketSnapshot | None = None
    indicators: IndicatorSnapshot | None = None
    technical_indicators: TechnicalIndicatorResponse | None = None
    result: StockAnalysisResult | None = None
    record_id: int | None = None
    notification_id: int | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()