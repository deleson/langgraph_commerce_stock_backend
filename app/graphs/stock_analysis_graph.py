from functools import lru_cache

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
def get_stock_analysis_graph():
    graph_builder = StateGraph(StockAnalysisState)

    _add_common_nodes(
        graph_builder=graph_builder,
        analyze_node=analyze_with_llm_node,
    )
    _add_common_edges(graph_builder)

    return graph_builder.compile()


@lru_cache
def get_stock_analysis_graph_async():
    graph_builder = StateGraph(StockAnalysisState)

    _add_common_nodes(
        graph_builder=graph_builder,
        analyze_node=analyze_with_llm_node_async,
    )
    _add_common_edges(graph_builder)

    return graph_builder.compile()


def run_stock_analysis_graph(initial_state: StockAnalysisState) -> StockAnalysisState:
    graph = get_stock_analysis_graph()
    return graph.invoke(initial_state)


async def arun_stock_analysis_graph(
    initial_state: StockAnalysisState,
) -> StockAnalysisState:
    graph = get_stock_analysis_graph_async()
    return await graph.ainvoke(initial_state)


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