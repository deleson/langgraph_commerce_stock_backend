from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.stock_analysis import MarketCode


ReactToolName = Literal[
    "get_analysis_record",
    "get_market_overview",
    "get_technical_indicators",
    "get_data_quality",
    "get_user_preference",
    "get_watchlist",
    "get_backtest_result",
    "get_stock_candidates",
]
ReactActionType = Literal[
    "tool_call",
    "final_answer",
    "error",
]


class ReactToolCall(BaseModel):
    tool_name: ReactToolName
    tool_input: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = Field(
        default=None,
        max_length=500,
        description="Why the agent wants to call this tool.",
    )


class ReactObservation(BaseModel):
    tool_name: ReactToolName
    tool_input: dict[str, Any] = Field(default_factory=dict)
    tool_output: dict[str, Any] | list[Any] | str | None = None
    success: bool = True
    error_message: str | None = Field(default=None, max_length=1000)
    created_at: datetime | None = None


class ReactToolTrace(BaseModel):
    step: int = Field(ge=1)
    action: ReactActionType
    tool_name: ReactToolName | None = None
    reason: str | None = Field(default=None, max_length=500)
    duration_ms: int | None = Field(default=None, ge=0)
    success: bool = True
    error_message: str | None = Field(default=None, max_length=1000)

class StockAnalysisReactFollowUpRequest(BaseModel):
    analysis_thread_id: str = Field(
        min_length=1,
        max_length=120,
        description="Business analysis thread id returned by stock analysis API.",
    )
    message: str = Field(
        min_length=1,
        max_length=1000,
        description="User follow-up question that may trigger ReAct tool calls.",
    )
    max_iterations: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Maximum ReAct reasoning/tool-call iterations.",
    )

    @field_validator("analysis_thread_id", "message", mode="before")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value


class StockAnalysisReactFollowUpResponse(BaseModel):
    analysis_thread_id: str
    react_graph_checkpoint_id: str | None = None
    answer: str
    used_tools: list[ReactToolName] = Field(default_factory=list)
    observations: list[ReactObservation] = Field(default_factory=list)
    trace: list[ReactToolTrace] = Field(default_factory=list)
    referenced_analysis_record_id: int | None = None
    referenced_symbol: str | None = None
    referenced_market: MarketCode | None = None
    created_at: datetime | None = None


class StockAnalysisReactGraphState(BaseModel):
    analysis_thread_id: str
    react_graph_checkpoint_id: str | None = None
    user_id: int
    message: str
    referenced_analysis_record_id: int | None = None
    referenced_symbol: str | None = None
    referenced_market: MarketCode | None = None
    context_snapshot: dict[str, Any] = Field(default_factory=dict)
    result_snapshot: dict[str, Any] = Field(default_factory=dict)
    user_profile_context: dict[str, Any] | None = None
    allowed_tools: list[ReactToolName] = Field(default_factory=list)
    next_action: ReactActionType | None = None
    tool_call: ReactToolCall | None = None
    observations: list[ReactObservation] = Field(default_factory=list)
    iteration_count: int = Field(default=0, ge=0)
    max_iterations: int = Field(default=3, ge=1, le=5)
    final_answer: str | None = None
    error_message: str | None = None
    trace: list[ReactToolTrace] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("analysis_thread_id", "message", mode="before")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value