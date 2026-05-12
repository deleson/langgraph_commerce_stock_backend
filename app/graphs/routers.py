from typing import Any

from app.graphs.states import StockAnalysisState
from app.schemas.stock_analysis import GraphRoute


_ALLOWED_GRAPH_ROUTES: set[GraphRoute] ={
    "normal",
    "degraded",
    "unavailable",
    "error",
}

def route_by_data_quality(state: StockAnalysisState) -> GraphRoute:
    """Choose the next graph branch based on market data quality.

    This function is intentionally side-effect free.
    It only reads StockAnalysisState and returns a route name for LangGraph.
    """
    graph_route = state.get("graph_route")
    if _is_valid_graph_route(graph_route):
        return graph_route

    quality_context = state.get("quality_context")
    if quality_context is not None and _is_valid_graph_route(quality_context.graph_route):
        return quality_context.graph_route

    if state.get("error_message"):
        return "error"

    return "degraded"

def _is_valid_graph_route(value: Any) -> bool:
    return value in _ALLOWED_GRAPH_ROUTES

