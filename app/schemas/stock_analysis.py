from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.technical_indicator import TechnicalIndicatorResponse

MarketCode = Literal["US", "CN", "HK"]
AnalysisType = Literal["stock_basic"]
TrendDirection = Literal["bullish", "bearish", "neutral"]
RiskLevel = Literal["low", "medium", "high"]


# service中发出请求的响应，调用图运转的请求参数
class StockAnalysisRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20, examples=["AAPL"])
    market: MarketCode = Field(examples=["US"])
    analysis_type: AnalysisType = Field(default="stock_basic")

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


# 图结构中的读取当前股票参数响应
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

# 图结构中的指标响应
class IndicatorSnapshot(BaseModel):
    price_change: float
    price_change_percent: float
    moving_average_5: float
    moving_average_20: float
    volatility_level: RiskLevel
    trend: TrendDirection


# 经过llm节点后的图结构分析响应
class StockAnalysisResult(BaseModel):
    summary: str
    risk_level: RiskLevel
    trend: TrendDirection
    key_points: list[str] = Field(default_factory=list)
    suggestion: str
    warnings: list[str] = Field(default_factory=list)


# 通过service调用图后的响应
class StockAnalysisResponse(BaseModel):
    record_id: int | None = None
    symbol: str
    market: MarketCode
    analysis_type: AnalysisType
    status: Literal["completed", "failed"]
    market_snapshot: MarketSnapshot
    indicators: IndicatorSnapshot
    result: StockAnalysisResult
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class StockAnalysisGraphState(BaseModel):
    user_id: int
    symbol: str
    market: MarketCode
    analysis_type: AnalysisType = "stock_basic"
    risk_preference: Literal["conservative", "balanced", "aggressive"] = "balanced"
    market_snapshot: MarketSnapshot | None = None
    indicators: IndicatorSnapshot | None = None
    technical_indicators: TechnicalIndicatorResponse | None = None
    result: StockAnalysisResult | None = None
    record_id: int | None = None
    notification_id: int | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)