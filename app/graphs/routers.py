"""主分析图的条件路由函数。

Router 只负责根据 state 返回下一个节点名称，不做数据库读写、不调用 LLM。
保持无副作用可以让图结构更容易测试，也避免路由阶段产生隐藏业务行为。
"""

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
    """根据数据质量选择主分析图下一条路线。

    优先使用 check_data_quality_node 写入的 graph_route；
    如果没有，则退回 quality_context 中的 graph_route；
    如果已有 error_message，则进入 error；
    最后兜底 degraded，避免缺失质量上下文时直接按 normal 分析。
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

