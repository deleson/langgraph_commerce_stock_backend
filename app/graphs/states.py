"""个股主分析 LangGraph 的状态结构。

LangGraph 节点之间不会直接传一堆函数参数，而是共同读写一个 state。
本文件定义的 StockAnalysisState 就是主分析图的“流程上下文”：它保存用户请求、
数据质量路线、行情快照、技术指标、策略信号、LLM 分析结果、持久化 id 和 AI 用量信息。

注意：这里不是 API 请求 / 响应 Schema，而是图内部运行时状态。
"""

from typing import Any, Literal, TypedDict

from app.schemas.stock_analysis import (
    GraphRoute,
    IndicatorSnapshot,
    MarketCode,
    MarketSnapshot,
    StockAnalysisContextSnapshot,
    StockAnalysisQualityContext,
    StockAnalysisResult,
)
from app.schemas.technical_indicator import TechnicalIndicatorResponse
from app.schemas.strategy_signal import StrategySignalResponse

class StockAnalysisState(TypedDict, total=False):
    """主分析图所有节点共享的运行时状态。

    它故意和 Pydantic API Schema 分开：
    API Schema 面向 HTTP 输入输出，Graph State 面向节点之间的数据流转。
    """

    # 请求与用户上下文：用于识别当前用户、股票、分析类型和图 checkpoint。
    user_id: int
    symbol: str
    market: MarketCode
    analysis_type: Literal["stock_basic"]
    risk_preference: Literal["conservative", "balanced", "aggressive"]
    thread_id: str

    # 图路由与数据质量：数据是否足够可信，决定 normal / degraded / unavailable / error 路线。
    graph_route: GraphRoute
    quality_context: StockAnalysisQualityContext
    route_reason: str
    degraded_reason: str

    # 行情与量化上下文：后续 LLM 只能基于这些后端准备好的事实与指标分析。
    market_snapshot: MarketSnapshot
    indicators: IndicatorSnapshot
    technical_indicators: TechnicalIndicatorResponse
    strategy_signal: StrategySignalResponse
    user_profile_context: dict[str, Any]
    relevant_memories_context: dict[str, Any]

    # LLM 或降级节点生成的最终分析结果。
    result: StockAnalysisResult

    # 普通追问的预留字段，主分析图本身不负责多轮 ReAct 工具调用。
    follow_up_message: str
    follow_up_answer: str

    # 持久化引用：Service 保存分析记录和通知后，会把 id 回填到 state。
    record_id: int
    notification_id: int
    context_snapshot: StockAnalysisContextSnapshot

    # AI 用量与额度：用于审计 DeepSeek 调用、成本估算和额度拦截。
    ai_quota_allowed: bool
    ai_quota_reason: str
    ai_usage_log_id: int

    # 错误与扩展信息：节点失败时尽量返回安全降级结果，而不是让异常穿透给用户。
    error_message: str
    metadata: dict[str, Any]
