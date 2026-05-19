from functools import lru_cache
from typing import TYPE_CHECKING
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.graphs.react_nodes import (
    agent_reason_node,
    create_react_tool_execution_node,
    final_answer_node,
)
from app.graphs.react_routers import route_react_action
from app.graphs.react_states import StockAnalysisReactState
from app.graphs.react_tools import get_default_react_tools

if TYPE_CHECKING:
    from app.services.stock_analysis_react_tool_service import (
        StockAnalysisReactToolService,
    )


@lru_cache
def get_stock_analysis_react_checkpointer() -> MemorySaver:
    """Return the in-memory checkpointer for ReAct graph runs.

    The checkpointer can be shared, but the graph itself is built with a
    request-scoped tool service.
    """

    return MemorySaver()


def get_stock_analysis_react_graph(
    tool_service: "StockAnalysisReactToolService",
):
    """Build a ReAct graph for one request-scoped tool service.

    The tool service holds database access and user-scoped business logic,
    so this graph should not be globally cached.
    """

    graph_builder = StateGraph(StockAnalysisReactState)
    tool_execution_node = create_react_tool_execution_node(tool_service)

    graph_builder.add_node("agent_reason", agent_reason_node)
    graph_builder.add_node("tool_execution", tool_execution_node)
    graph_builder.add_node("final_answer", final_answer_node)

    graph_builder.add_edge(START, "agent_reason")

    graph_builder.add_conditional_edges(
        "agent_reason",
        route_react_action,
        {
            "get_analysis_record": "tool_execution",
            "get_market_overview": "tool_execution",
            "get_technical_indicators": "tool_execution",
            "get_data_quality": "tool_execution",
            "get_user_preference": "tool_execution",
            "get_watchlist": "tool_execution",
            "get_backtest_result": "tool_execution",
            "final_answer": "final_answer",
            "error": "final_answer",
        },
    )

    graph_builder.add_edge("tool_execution", "agent_reason")
    graph_builder.add_edge("final_answer", END)

    return graph_builder.compile(
        checkpointer=get_stock_analysis_react_checkpointer(),
    )


async def arun_stock_analysis_react_graph(
    initial_state: StockAnalysisReactState,
    *,
    tool_service: "StockAnalysisReactToolService",
    react_graph_checkpoint_id: str | None = None,
) -> StockAnalysisReactState:
    """Run the async ReAct graph.

    analysis_thread_id is the business conversation id shared with the
    analysis record. react_graph_checkpoint_id is only for this ReAct graph's
    LangGraph checkpoint.
    """

    graph = get_stock_analysis_react_graph(tool_service)
    config = _build_react_graph_config(
        initial_state,
        react_graph_checkpoint_id=react_graph_checkpoint_id,
    )

    return await graph.ainvoke(
        _prepare_initial_react_state(initial_state, config),
        config,
    )


def _build_react_graph_config(
    initial_state: StockAnalysisReactState,
    *,
    react_graph_checkpoint_id: str | None,
) -> dict:
    resolved_checkpoint_id = (
        react_graph_checkpoint_id
        or initial_state.get("react_graph_checkpoint_id")
        or _build_default_react_checkpoint_id(initial_state)
    )

    return {
        "configurable": {
            "thread_id": resolved_checkpoint_id,
        },
    }


def _build_default_react_checkpoint_id(
    initial_state: StockAnalysisReactState,
) -> str:
    analysis_thread_id = initial_state.get("analysis_thread_id")
    if not analysis_thread_id:
        raise ValueError("analysis_thread_id is required for ReAct graph")

    return f"react:{analysis_thread_id}:{uuid4().hex}"


def _prepare_initial_react_state(
    initial_state: StockAnalysisReactState,
    config: dict,
) -> StockAnalysisReactState:
    checkpoint_id = config["configurable"]["thread_id"]

    prepared_state: StockAnalysisReactState = {
        "allowed_tools": get_default_react_tools(),
        "observations": [],
        "trace": [],
        "iteration_count": 0,
        "max_iterations": 3,
        "metadata": {},
        **initial_state,
        "react_graph_checkpoint_id": checkpoint_id,
    }

    if not prepared_state.get("allowed_tools"):
        prepared_state["allowed_tools"] = get_default_react_tools()

    if prepared_state.get("observations") is None:
        prepared_state["observations"] = []

    if prepared_state.get("trace") is None:
        prepared_state["trace"] = []

    if prepared_state.get("metadata") is None:
        prepared_state["metadata"] = {}

    return prepared_state