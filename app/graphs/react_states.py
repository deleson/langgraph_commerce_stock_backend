"""ReAct 追问图的状态结构。

ReAct 图用于“主分析之后的多轮工具追问”。
它和主分析图不同：主分析图负责生成第一份分析；ReAct 图负责在已有分析线程上，
让模型判断是否需要调用白名单工具，并把 Observation、Trace 和最终回答保存下来。

注意：state 中的 allowed_tools 只是允许工具名，真正执行仍由后端 Tool Service 完成。
"""

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
    """ReAct 图所有节点共享的运行时状态。

    它只服务于 ReAct 追问图，不应和主分析图 StockAnalysisState 混用。
    analysis_thread_id 是业务会话 id；react_graph_checkpoint_id 只是 LangGraph 运行 id。
    """

    # 业务身份：用于把追问绑定到已有分析线程，并区分图 checkpoint。
    analysis_thread_id: str
    react_graph_checkpoint_id: str

    # 当前用户与问题：工具执行和消息持久化都必须按 user_id 隔离。
    user_id: int
    message: str

    # 被追问引用的主分析记录。
    referenced_analysis_record_id: int
    referenced_symbol: str
    referenced_market: MarketCode

    # 从主分析记录、历史会话、用户画像和相关记忆中提取的上下文。
    context_snapshot: dict[str, Any]
    result_snapshot: dict[str, Any]
    conversation_context: dict[str, Any]
    user_profile_context: dict[str, Any]
    relevant_memories_context: dict[str, Any]

    # 工具控制：LLM 只能在 allowed_tools 中选择工具，不能自由调用任意函数。
    allowed_tools: list[ReactToolName]
    next_action: ReactActionType | None
    tool_call: ReactToolCall | None

    # ReAct 循环状态：Observation 会回流给下一轮 agent_reason。
    observations: Annotated[list[ReactObservation], operator.add]
    iteration_count: int
    max_iterations: int

    # 最终面向用户的回答。
    final_answer: str

    # AI 用量与额度：ReAct reason 和 final_answer 都会分别记录。
    ai_quota_allowed: bool
    ai_quota_reason: str
    ai_usage_log_ids: Annotated[list[int], operator.add]

    # 错误和 Trace：Trace 用于审计模型为什么调用了哪些工具。
    error_message: str
    trace: Annotated[list[ReactToolTrace], operator.add]
    metadata: dict[str, Any]
