"""个股分析 ReAct 追问 LangGraph 图结构。

ReAct 图的核心循环是：
agent_reason 判断下一步是否需要工具；
tool_execution 执行后端白名单工具并产生 Observation；
Observation 回到 agent_reason；
最后进入 final_answer 生成回答。

这个图不会让 AI 任意访问数据库。工具执行必须通过 request-scoped
StockAnalysisReactToolService，并且工具内部继续做 user_id 隔离。
"""

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
    """返回 ReAct 图的内存 checkpoint。

    checkpointer 可以共享；但图本身依赖每次请求的 tool_service，
    因此不能把完整 ReAct graph 做全局缓存。
    """

    return MemorySaver()


def get_stock_analysis_react_graph(
    tool_service: "StockAnalysisReactToolService",
):
    """为一次请求构建 ReAct 图。

    tool_service 持有数据库 Session 和当前请求范围内的业务能力，
    这样工具执行时仍然受后端用户隔离和参数限制保护。
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
            "get_stock_candidates": "tool_execution",
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
    """执行异步 ReAct 图。

    analysis_thread_id 是业务分析线程 id；
    react_graph_checkpoint_id 只是本次 ReAct 图运行的 checkpoint id。
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
    """生成 ReAct 图 checkpoint 配置。"""

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
    """当调用方未提供 checkpoint id 时，为本次 ReAct 运行生成默认 id。"""

    analysis_thread_id = initial_state.get("analysis_thread_id")
    if not analysis_thread_id:
        raise ValueError("analysis_thread_id is required for ReAct graph")

    return f"react:{analysis_thread_id}:{uuid4().hex}"


def _prepare_initial_react_state(
    initial_state: StockAnalysisReactState,
    config: dict,
) -> StockAnalysisReactState:
    """补齐 ReAct 初始 state 的默认值。

    max_iterations 控制工具调用循环上限，避免模型反复调用工具导致成本失控。
    """

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
