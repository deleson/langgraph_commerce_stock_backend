from functools import lru_cache

from langgraph.graph import END,START,StateGraph

from app.graphs.nodes import (
    analyze_with_llm_node,
    calculate_indicators_node,
    load_market_data_node,
)
from app.graphs.states import StockAnalysisState

@lru_cache
def get_stock_analysis_graph():
    graph_builder = StateGraph(StockAnalysisState)

    graph_builder.add_node("load_market_data",load_market_data_node)
    graph_builder.add_node("calculate_indicators_node",calculate_indicators_node)
    graph_builder.add_node("analyze_with_llm_node",analyze_with_llm_node)

    graph_builder.add_edge(START,"load_market_data")
    graph_builder.add_edge("load_market_data","calculate_indicators_node")
    graph_builder.add_edge("calculate_indicators_node","analyze_with_llm_node")
    graph_builder.add_edge("analyze_with_llm_node",END)

    return graph_builder.compile()

def run_stock_analysis_graph(initial_state:StockAnalysisState) -> StockAnalysisState:
    graph = get_stock_analysis_graph()
    return graph.invoke(initial_state)