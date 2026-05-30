import operator
from typing import Annotated, Any, TypedDict


from app.schemas.stock_analysis import MarketCode
from app.schemas.stock_analysis_react import (
    ReactActionType,
    ReactObservation,
    ReactToolCall,
    ReactToolName,
    ReactToolTrace,
)


class StockAnalysisReactState(TypedDict, total=False):
    """Runtime state shared by stock analysis ReAct graph nodes.

    This state is only for the ReAct follow-up graph.
    It should not be mixed with StockAnalysisState from the main analysis graph.
    """

    # Business identity.
    analysis_thread_id: str
    react_graph_checkpoint_id: str

    # Current user and question.
    user_id: int
    message: str

    # Referenced analysis record.
    referenced_analysis_record_id: int
    referenced_symbol: str
    referenced_market: MarketCode

    # Context loaded from AnalysisRecord.
    context_snapshot: dict[str, Any]
    result_snapshot: dict[str, Any]
    conversation_context: dict[str, Any]
    user_profile_context: dict[str, Any]
    relevant_memories_context: dict[str, Any]

    # Tool control.
    allowed_tools: list[ReactToolName]
    next_action: ReactActionType | None
    tool_call: ReactToolCall | None

    # ReAct loop state.
    observations: Annotated[list[ReactObservation], operator.add]
    iteration_count: int
    max_iterations: int

    # Final output.
    final_answer: str

    # AI usage and quota.
    ai_quota_allowed: bool
    ai_quota_reason: str
    ai_usage_log_ids: Annotated[list[int], operator.add]

    # Error and trace.
    error_message: str
    trace: Annotated[list[ReactToolTrace], operator.add]
    metadata: dict[str, Any]