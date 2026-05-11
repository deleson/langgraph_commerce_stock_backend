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

    # Analysis output.
    result: StockAnalysisResult

    # Follow-up placeholders for later steps.
    follow_up_message: str
    follow_up_answer: str

    # Persistence references.
    record_id: int
    notification_id: int
    context_snapshot: StockAnalysisContextSnapshot

    # Error and extension fields.
    error_message: str
    metadata: dict[str, Any]