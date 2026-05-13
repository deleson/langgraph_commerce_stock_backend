from functools import lru_cache

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.graphs.nodes import (
    analyze_with_llm_node,
    analyze_with_llm_node_async,
    build_data_unavailable_result_node,
    calculate_indicators_node,
    check_data_quality_node,
    load_market_data_node,
    load_technical_indicators_node,
    prepare_degraded_context_node,
)
from app.graphs.routers import route_by_data_quality
from app.graphs.states import StockAnalysisState


@lru_cache
def get_stock_analysis_checkpointer() -> MemorySaver:
    return MemorySaver()


@lru_cache
def get_stock_analysis_graph():
    graph_builder = StateGraph(StockAnalysisState)

    _add_common_nodes(
        graph_builder=graph_builder,
        analyze_node=analyze_with_llm_node,
    )
    _add_common_edges(graph_builder)

    return graph_builder.compile(
        checkpointer=get_stock_analysis_checkpointer(),
    )


@lru_cache
def get_stock_analysis_graph_async():
    graph_builder = StateGraph(StockAnalysisState)

    _add_common_nodes(
        graph_builder=graph_builder,
        analyze_node=analyze_with_llm_node_async,
    )
    _add_common_edges(graph_builder)

    return graph_builder.compile(
        checkpointer=get_stock_analysis_checkpointer(),
    )


def run_stock_analysis_graph(
    initial_state: StockAnalysisState,
    *,
    thread_id: str | None = None,
) -> StockAnalysisState:
    graph = get_stock_analysis_graph()
    config = _build_graph_config(initial_state, thread_id=thread_id)

    return graph.invoke(
        _ensure_thread_id(initial_state, config),
        config,
    )


async def arun_stock_analysis_graph(
    initial_state: StockAnalysisState,
    *,
    thread_id: str | None = None,
) -> StockAnalysisState:
    graph = get_stock_analysis_graph_async()
    config = _build_graph_config(initial_state, thread_id=thread_id)

    return await graph.ainvoke(
        _ensure_thread_id(initial_state, config),
        config,
    )


def get_stock_analysis_graph_state(
    *,
    thread_id: str,
):
    graph = get_stock_analysis_graph_async()
    return graph.get_state(
        {
            "configurable": {
                "thread_id": thread_id,
            },
        }
    )


def _build_graph_config(
    initial_state: StockAnalysisState,
    *,
    thread_id: str | None,
) -> dict:
    resolved_thread_id = thread_id or initial_state.get("thread_id")

    if not resolved_thread_id:
        raise ValueError("thread_id is required when graph checkpointing is enabled")

    return {
        "configurable": {
            "thread_id": resolved_thread_id,
        },
    }


def _ensure_thread_id(
    initial_state: StockAnalysisState,
    config: dict,
) -> StockAnalysisState:
    thread_id = config["configurable"]["thread_id"]

    return {
        **initial_state,
        "thread_id": thread_id,
    }


def _add_common_nodes(
    *,
    graph_builder: StateGraph,
    analyze_node,
) -> None:
    graph_builder.add_node("check_data_quality", check_data_quality_node)
    graph_builder.add_node("prepare_degraded_context", prepare_degraded_context_node)
    graph_builder.add_node("build_data_unavailable_result", build_data_unavailable_result_node)
    graph_builder.add_node("load_market_data", load_market_data_node)
    graph_builder.add_node("calculate_indicators", calculate_indicators_node)
    graph_builder.add_node("load_technical_indicators", load_technical_indicators_node)
    graph_builder.add_node("analyze_with_llm", analyze_node)


def _add_common_edges(
    graph_builder: StateGraph,
) -> None:
    graph_builder.add_edge(START, "check_data_quality")

    graph_builder.add_conditional_edges(
        "check_data_quality",
        route_by_data_quality,
        {
            "normal": "load_market_data",
            "degraded": "prepare_degraded_context",
            "unavailable": "build_data_unavailable_result",
            "error": "build_data_unavailable_result",
        },
    )

    graph_builder.add_edge("prepare_degraded_context", "load_market_data")
    graph_builder.add_edge("load_market_data", "calculate_indicators")
    graph_builder.add_edge("calculate_indicators", "load_technical_indicators")
    graph_builder.add_edge("load_technical_indicators", "analyze_with_llm")
    graph_builder.add_edge("analyze_with_llm", END)
    graph_builder.add_edge("build_data_unavailable_result", END)