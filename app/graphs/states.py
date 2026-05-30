from typing import Any, Literal, TypedDict

from app.schemas.stock_analysis import (
    GraphRoute,
    IndicatorSnapshot,
    MarketCode,
    MarketSnapshot,
    StockAnalysisContextSnapshot,
    StockAnalysisQualityContext,
    StockAnalysisResult,
)
from app.schemas.technical_indicator import TechnicalIndicatorResponse
from app.schemas.strategy_signal import StrategySignalResponse

class StockAnalysisState(TypedDict, total=False):
    """Runtime state shared by stock analysis graph nodes.

    This TypedDict is the internal working state of LangGraph.
    It is intentionally separate from Pydantic API schemas.
    """

    # Request and user context.
    user_id: int
    symbol: str
    market: MarketCode
    analysis_type: Literal["stock_basic"]
    risk_preference: Literal["conservative", "balanced", "aggressive"]
    thread_id: str

    # Graph routing and data quality context.
    graph_route: GraphRoute
    quality_context: StockAnalysisQualityContext
    route_reason: str
    degraded_reason: str

    # Market and indicator context.
    market_snapshot: MarketSnapshot
    indicators: IndicatorSnapshot
    technical_indicators: TechnicalIndicatorResponse
    strategy_signal: StrategySignalResponse
    user_profile_context: dict[str, Any]
    relevant_memories_context: dict[str, Any]

    # Analysis output.
    result: StockAnalysisResult

    # Follow-up placeholders for later steps.
    follow_up_message: str
    follow_up_answer: str

    # Persistence references.
    record_id: int
    notification_id: int
    context_snapshot: StockAnalysisContextSnapshot

    # AI usage and quota.
    ai_quota_allowed: bool
    ai_quota_reason: str
    ai_usage_log_id: int

    # Error and extension fields.
    error_message: str
    metadata: dict[str, Any]