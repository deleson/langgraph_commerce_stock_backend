"""个股主分析 LangGraph 图结构。

主分析图不是“直接把用户问题丢给 LLM”。
它会先检查数据质量，再根据路线决定是否继续加载行情、指标和策略信号：

1. normal：数据可用，进入完整 AI 分析；
2. degraded：数据可用但有风险，带着降级上下文进入 AI 分析；
3. unavailable / error：数据不可用或出错，不调用 LLM，直接生成安全结果。

这样可以避免在行情缺失、过旧或质量不足时让 AI 编造分析。
"""

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
    """返回主分析图的内存 checkpoint。

    checkpoint 用于 LangGraph 识别同一条分析线程。
    当前第一版使用 MemorySaver，生产分析结果仍以 analysis_records 表为准。
    """

    return MemorySaver()


@lru_cache
def get_stock_analysis_graph():
    """构建同步版本主分析图。

    同步版本保留给早期兼容路径；当前 API 主链路更常使用 async 图。
    """

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
    """构建异步版本主分析图。

    异步版本用于真实 API 链路，可以等待数据库、行情服务和 DeepSeek 调用。
    """

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
    """执行同步主分析图。"""

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
    """执行异步主分析图。"""

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
    """读取指定 thread_id 的图 checkpoint 状态。"""

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
    """生成 LangGraph checkpoint 配置。

    thread_id 是分析线程 id，也是图 checkpoint 的关键标识。
    """

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
    """确保 state 中带有最终解析出的 thread_id。"""

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
    """注册主分析图的公共节点。

    同步图和异步图只有 LLM 分析节点不同，其他节点顺序保持一致。
    """

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
    """注册主分析图边和条件路由。

    数据质量节点是第一道门：
    normal / degraded 才继续走行情与 LLM；
    unavailable / error 会直接进入不可用结果节点。
    """

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
