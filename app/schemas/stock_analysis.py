"""个股 AI 主分析 Schema。

本文件定义主分析请求、市场快照、指标快照、质量上下文、图状态和响应结构。
真实数据加载、质量路由和 DeepSeek 调用在 Service / LangGraph 节点中完成。
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.market_data_sync import MarketDataQualityReport
from app.schemas.technical_indicator import TechnicalIndicatorResponse
from app.schemas.strategy_signal import StrategySignalResponse

MarketCode = Literal["US", "CN", "HK"]
AnalysisType = Literal["stock_basic"]
TrendDirection = Literal["bullish", "bearish", "neutral"]
RiskLevel = Literal["low", "medium", "high"]
GraphRoute = Literal["normal", "degraded", "unavailable", "error", "quota_blocked"]


class StockAnalysisRequest(BaseModel):
    """个股 AI 分析请求体。"""

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
    """主分析图使用的行情快照。"""

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
    """主分析图兼容早期逻辑的基础指标快照。"""

    price_change: float
    price_change_percent: float
    moving_average_5: float
    moving_average_20: float
    volatility_level: RiskLevel
    trend: TrendDirection


class StockAnalysisResult(BaseModel):
    """LLM 结构化分析结果。"""

    summary: str
    risk_level: RiskLevel
    trend: TrendDirection
    key_points: list[str] = Field(default_factory=list)
    suggestion: str
    warnings: list[str] = Field(default_factory=list)


class StockAnalysisQualityContext(BaseModel):
    """主分析图的数据质量上下文。"""

    data_quality: MarketDataQualityReport | None = None
    graph_route: GraphRoute | None = None
    route_reason: str | None = Field(default=None, max_length=500)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class StockAnalysisContextSnapshot(BaseModel):
    """主分析图执行过程的上下文快照。"""

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
    strategy_signal: StrategySignalResponse | None = None
    user_profile_context: dict[str, Any] | None = None
    relevant_memories_context: dict[str, Any] | None = None
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
    """个股 AI 主分析响应体。"""

    record_id: int | None = None
    thread_id: str | None = None
    symbol: str
    market: MarketCode
    analysis_type: AnalysisType
    status: Literal["completed", "failed"]
    graph_route: GraphRoute | None = None
    quality_context: StockAnalysisQualityContext | None = None
    market_snapshot: MarketSnapshot | None = None
    indicators: IndicatorSnapshot | None = None
    result: StockAnalysisResult
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class StockAnalysisFollowUpRequest(BaseModel):
    """普通追问请求体。

    普通追问基于已有分析线程回答，不执行 ReAct 工具循环。
    """

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
    """普通追问响应体。"""

    thread_id: str
    answer: str
    referenced_analysis_record_id: int | None = None
    referenced_symbol: str | None = None
    referenced_market: MarketCode | None = None
    created_at: datetime | None = None


class StockAnalysisGraphState(BaseModel):
    """主分析 LangGraph 的状态结构。"""

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
    strategy_signal: StrategySignalResponse | None = None
    user_profile_context: dict[str, Any] | None = None
    relevant_memories_context: dict[str, Any] | None = None
    result: StockAnalysisResult | None = None
    record_id: int | None = None
    notification_id: int | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()
