from typing import Any,Literal,TypedDict

from app.schemas.stock_analysis import (
    IndicatorSnapshot,
    MarketSnapshot,
    MarketCode,
    StockAnalysisResult,
)

class StockAnalysisState(TypedDict,total=False):
    """Runtime state shared by stage-five stock analysis graph nodes."""
    user_id: int
    symbol: str
    market: MarketCode
    analysis_type: Literal["stock_basic"]
    risk_preference: Literal["conservative","balanced","aggressive"]

    market_snapshot: MarketSnapshot
    indicators: IndicatorSnapshot
    result: StockAnalysisResult

    record_id: int
    notification_id: int
    error_message: str
    meatdata: dict[str,Any]

