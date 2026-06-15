"""个股主分析图节点实现。

本文件中的每个函数都是 LangGraph 的一个节点或辅助函数。
主分析链路的核心原则是：

1. 先检查数据质量，再决定是否进入 AI；
2. 让 LLM 只基于后端准备好的行情、指标、策略信号、用户画像和记忆上下文分析；
3. 额度不足、数据不可用、LLM 异常时返回安全降级结果；
4. 所有 AI 调用都记录用量，便于成本控制和审计。

注意：这里的 buy / sell / risk 等内容都是研究辅助，不构成投资建议。
"""

import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.core.exceptions import BadRequestException
from app.core.llm import get_chat_model
from app.graphs.states import StockAnalysisState
from app.schemas.stock_analysis import (
    GraphRoute,
    StockAnalysisQualityContext,
    StockAnalysisResult,
)
from app.services.indicator_service import IndicatorService
from app.services.market_data_service import MockMarketDataService
from langchain_core.messages import HumanMessage, SystemMessage
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.repositories.ai_usage_repo import AsyncAIUsageRepository
from app.schemas.ai_usage import AIQuotaCheckRequest
from app.services.ai_quota_service import AIQuotaService
from app.services.ai_usage_service import AIUsageService
from app.services.ai_usage_token_service import (
    AIUsageCostEstimate,
    AIUsageTokenEstimate,
    AIUsageTokenService,
)
from app.services.ai_quota_message_service import AIQuotaMessageService

logger = logging.getLogger(__name__)
STOCK_ANALYSIS_AI_FEATURE = "stock_analysis"
STOCK_ANALYSIS_ESTIMATED_COMPLETION_TOKENS = 1000


def load_market_data_node(state: StockAnalysisState) -> StockAnalysisState:
    """加载主分析所需的行情快照。

    当前节点仍使用 MockMarketDataService 获取基础快照；
    真实 K 线、数据质量、技术指标和策略信号由 Service 层提前写入 state。
    """

    symbol = state.get("symbol")
    market = state.get("market")

    if symbol is None or market is None:
        raise BadRequestException(message="symbol and market are required")

    market_snapshot = MockMarketDataService().get_snapshot(
        symbol=symbol,
        market=market,
    )

    return {
        "symbol": market_snapshot.symbol,
        "market_snapshot": market_snapshot,
    }


def calculate_indicators_node(state: StockAnalysisState) -> StockAnalysisState:
    """基于行情快照计算早期基础指标。

    该节点服务于主分析图兼容路径；更完整的 MA、RSI、MACD 等指标来自
    TechnicalIndicatorQueryService 并通过 load_technical_indicators_node 注入上下文。
    """

    market_snapshot = state.get("market_snapshot")

    if market_snapshot is None:
        raise BadRequestException(message="market_snapshot is required")

    indicators = IndicatorService().calculate(market_snapshot)

    return {
        "indicators": indicators,
    }


def load_technical_indicators_node(state: StockAnalysisState) -> StockAnalysisState:
    """把 Service 层准备好的技术指标写入图 metadata。

    节点本身不重新计算指标，只整理上下文和 warning，供后续 LLM Prompt 使用。
    """

    technical_indicators = state.get("technical_indicators")
    metadata = state.get("metadata", {})

    if technical_indicators is None:
        return {
            "metadata": {
                **metadata,
                "technical_indicators_context": {
                    "available": False,
                    "reason": "technical indicators are not available in graph state",
                },
            },
        }

    warnings = _build_technical_indicator_warnings(state)

    return {
        "technical_indicators": technical_indicators,
        "metadata": {
            **metadata,
            "technical_indicators_context": {
                "available": True,
                "symbol": technical_indicators.symbol,
                "market": technical_indicators.market,
                "timeframe": technical_indicators.timeframe,
                "source": technical_indicators.source,
                "candle_count": technical_indicators.candle_count,
                "adjust_type": technical_indicators.adjust_type,
                "calculated_at": technical_indicators.calculated_at.isoformat(),
                "warnings": warnings,
            },
        },
    }


def _build_technical_indicator_warnings(state: StockAnalysisState) -> list[str]:
    technical_indicators = state.get("technical_indicators")
    if technical_indicators is None:
        return ["未获取到完整技术指标上下文。"]

    warnings = [
        *technical_indicators.summary.warnings,
    ]

    quality_context = state.get("quality_context")
    if quality_context is not None:
        warnings.extend(quality_context.warnings)

        if quality_context.data_quality is not None:
            warnings.extend(quality_context.data_quality.warnings)

    if state.get("graph_route") == "degraded":
        degraded_reason = state.get("degraded_reason")
        if degraded_reason:
            warnings.append(degraded_reason)

    return _deduplicate_messages(warnings)


def check_data_quality_node(state: StockAnalysisState) -> StockAnalysisState:
    """检查行情数据质量并写入图路由。

    数据质量是主分析图的第一道门：
    数据可用才走 normal；
    数据有风险但仍可参考时走 degraded；
    数据为空、不足、过旧或错误时走 unavailable / error。
    """

    quality_context = state.get("quality_context")

    if quality_context is None:
        route: GraphRoute = "degraded"
        reason = "market data quality context is missing"

        fallback_context = StockAnalysisQualityContext(
            graph_route=route,
            route_reason=reason,
            warnings=["未获取到行情数据质量报告，本次分析将按降级模式处理。"],
            errors=[],
        )

        return {
            "graph_route": route,
            "quality_context": fallback_context,
            "route_reason": reason,
            "degraded_reason": reason,
        }

    route, reason = _resolve_quality_route(quality_context)

    updated_context = quality_context.model_copy(
        update={
            "graph_route": route,
            "route_reason": reason,
        },
        deep=True,
    )

    next_state: StockAnalysisState = {
        "graph_route": route,
        "quality_context": updated_context,
        "route_reason": reason,
    }

    if route == "degraded":
        next_state["degraded_reason"] = reason

    if route in {"unavailable", "error"}:
        next_state["error_message"] = reason

    return next_state


def prepare_degraded_context_node(state: StockAnalysisState) -> StockAnalysisState:
    """准备降级分析上下文。

    degraded 不代表完全不可用，而是提醒后续 LLM：
    当前数据存在数量不足、过旧、同步异常等风险，回答必须更谨慎。
    """

    quality_context = state.get("quality_context")
    degraded_reason = _resolve_degraded_reason(state)

    warnings = _resolve_degraded_warnings(state)

    metadata = {
        **state.get("metadata", {}),
        "degraded_analysis": {
            "enabled": True,
            "reason": degraded_reason,
            "warnings": warnings,
        },
    }

    if quality_context is not None:
        quality_context = quality_context.model_copy(
            update={
                "graph_route": "degraded",
                "route_reason": degraded_reason,
                "warnings": _deduplicate_messages(
                    [
                        *quality_context.warnings,
                        *warnings,
                    ]
                ),
            },
            deep=True,
        )

    return {
        "graph_route": "degraded",
        "quality_context": quality_context,
        "degraded_reason": degraded_reason,
        "route_reason": degraded_reason,
        "metadata": metadata,
    }


def build_data_unavailable_result_node(state: StockAnalysisState) -> StockAnalysisState:
    """构造数据不可用时的安全结果。

    这里不会调用 LLM，避免在没有可靠行情和指标时让 AI 编造分析。
    """

    reason = _resolve_unavailable_reason(state)
    warnings = _resolve_unavailable_warnings(state)

    metadata = {
        **state.get("metadata", {}),
        "unavailable_analysis": {
            "enabled": True,
            "reason": reason,
            "warnings": warnings,
        },
    }

    quality_context = state.get("quality_context")
    if quality_context is not None:
        quality_context = quality_context.model_copy(
            update={
                "graph_route": "unavailable",
                "route_reason": reason,
                "errors": _deduplicate_messages(
                    [
                        *quality_context.errors,
                        reason,
                    ]
                ),
                "warnings": _deduplicate_messages(
                    [
                        *quality_context.warnings,
                        *warnings,
                    ]
                ),
            },
            deep=True,
        )

    result = StockAnalysisResult(
        summary="当前行情数据不足或不可用，暂时无法生成可靠的股票分析。",
        risk_level="medium",
        trend="neutral",
        key_points=[
            "系统未能获得足够可靠的行情数据。",
            "为了避免误导，本次不进行强趋势判断。",
        ],
        suggestion="建议先同步或补充行情数据后再重新发起分析。",
        warnings=warnings,
    )

    return {
        "graph_route": "unavailable",
        "quality_context": quality_context,
        "route_reason": reason,
        "error_message": reason,
        "result": result,
        "metadata": metadata,
    }


def _resolve_unavailable_reason(state: StockAnalysisState) -> str:
    error_message = state.get("error_message")
    if error_message:
        return error_message

    route_reason = state.get("route_reason")
    if route_reason:
        return route_reason

    quality_context = state.get("quality_context")
    if quality_context is not None:
        if quality_context.errors:
            return _join_messages(quality_context.errors)

        if quality_context.route_reason:
            return quality_context.route_reason

        if quality_context.data_quality is not None:
            data_quality = quality_context.data_quality

            if data_quality.errors:
                return _join_messages(data_quality.errors)

            if data_quality.is_empty:
                return f"market candles are empty for {data_quality.market}:{data_quality.symbol}"

    return "market data is unavailable"


def _resolve_unavailable_warnings(state: StockAnalysisState) -> list[str]:
    warnings: list[str] = []

    reason = _resolve_unavailable_reason(state)
    warnings.append(reason)

    quality_context = state.get("quality_context")
    if quality_context is not None:
        warnings.extend(quality_context.warnings)
        warnings.extend(quality_context.errors)

        if quality_context.data_quality is not None:
            warnings.extend(quality_context.data_quality.warnings)
            warnings.extend(quality_context.data_quality.errors)

            if quality_context.data_quality.is_empty:
                warnings.append("未查询到可用于分析的行情 K 线数据。")

    warnings.append("本次未调用大模型生成强分析结论，以避免基于缺失数据误导用户。")
    warnings.append("该结果不构成投资建议。")

    return _deduplicate_messages(warnings)


def _resolve_degraded_reason(state: StockAnalysisState) -> str:
    degraded_reason = state.get("degraded_reason")
    if degraded_reason:
        return degraded_reason

    route_reason = state.get("route_reason")
    if route_reason:
        return route_reason

    quality_context = state.get("quality_context")
    if quality_context is not None:
        if quality_context.route_reason:
            return quality_context.route_reason

        if quality_context.warnings:
            return _join_messages(quality_context.warnings)

        if quality_context.data_quality is not None and quality_context.data_quality.warnings:
            return _join_messages(quality_context.data_quality.warnings)

    return "market data quality is uncertain"


def _resolve_degraded_warnings(state: StockAnalysisState) -> list[str]:
    warnings: list[str] = []

    degraded_reason = state.get("degraded_reason")
    if degraded_reason:
        warnings.append(degraded_reason)

    route_reason = state.get("route_reason")
    if route_reason:
        warnings.append(route_reason)

    quality_context = state.get("quality_context")
    if quality_context is not None:
        warnings.extend(quality_context.warnings)

        if quality_context.data_quality is not None:
            warnings.extend(quality_context.data_quality.warnings)

            if not quality_context.data_quality.is_enough:
                warnings.append("行情 K 线数量不足，分析结论需要降低置信度。")

            if quality_context.data_quality.is_stale:
                warnings.append("行情 K 线数据可能过旧，分析结论存在时效性风险。")

    warnings.append("本次为降级分析，不构成投资建议。")

    return _deduplicate_messages(warnings)


def _resolve_quality_route(
    quality_context: StockAnalysisQualityContext,
) -> tuple[GraphRoute, str]:
    if quality_context.errors:
        return "unavailable", _join_messages(quality_context.errors)

    data_quality = quality_context.data_quality

    if data_quality is None:
        warnings = quality_context.warnings or ["market data quality report is missing"]
        return "degraded", _join_messages(warnings)

    if data_quality.errors:
        return "unavailable", _join_messages(data_quality.errors)

    if data_quality.is_empty:
        return (
            "unavailable",
            f"market candles are empty for {data_quality.market}:{data_quality.symbol}",
        )

    warnings = [
        *quality_context.warnings,
        *data_quality.warnings,
    ]

    if not data_quality.is_enough:
        warnings.append("market candle count is not enough")

    if data_quality.is_stale:
        warnings.append("market candle data is stale")

    warnings = _deduplicate_messages(warnings)

    if warnings:
        return "degraded", _join_messages(warnings)

    return "normal", "market data quality is acceptable"


def _deduplicate_messages(messages: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for message in messages:
        normalized = str(message).strip()
        if not normalized or normalized in seen:
            continue

        result.append(normalized)
        seen.add(normalized)

    return result


def _join_messages(messages: list[str]) -> str:
    cleaned_messages = _deduplicate_messages(messages)
    return "; ".join(cleaned_messages) if cleaned_messages else "unknown reason"


def analyze_with_llm_node(state: StockAnalysisState) -> StockAnalysisState:
    """同步 LLM 分析节点。

    保留给早期同步调用路径。真实生产 API 主要使用异步版本，
    但两者都遵循同一 Prompt 和结构化解析规则。
    """

    market_snapshot = state.get("market_snapshot")
    indicators = state.get("indicators")

    if market_snapshot is None or indicators is None:
        return _build_llm_error_result_state(
            state=state,
            reason="market_snapshot and indicators are required before LLM analysis",
        )

    risk_preference = state.get("risk_preference", "balanced")

    messages = _build_stock_analysis_messages(
        symbol=market_snapshot.symbol,
        market=market_snapshot.market,
        risk_preference=risk_preference,
        market_data=market_snapshot.model_dump(mode="json"),
        indicators=indicators.model_dump(mode="json"),
        user_profile_context=state.get("user_profile_context"),
        relevant_memories_context=state.get("relevant_memories_context"),
    )

    try:
        llm = get_chat_model()
        response = llm.invoke(messages)
        result = _parse_stock_analysis_result(response.content)
    except Exception as exc:
        logger.exception("stock analysis sync llm node failed")
        return _build_llm_error_result_state(
            state=state,
            reason=_safe_exception_message(exc),
        )

    return {
        "result": result,
    }


async def analyze_with_llm_node_async(state: StockAnalysisState) -> StockAnalysisState:
    """异步 LLM 分析节点。

    这是主分析生产链路的 AI 节点：先做额度预检查，再调用 DeepSeek，
    成功时记录 success 用量，失败时记录 failed 并返回降级结果。
    """

    market_snapshot = state.get("market_snapshot")
    indicators = state.get("indicators")

    if market_snapshot is None or indicators is None:
        return _build_llm_error_result_state(
            state=state,
            reason="market_snapshot and indicators are required before LLM analysis",
        )

    user_id = state.get("user_id")
    if user_id is None:
        return _build_llm_error_result_state(
            state=state,
            reason="user_id is required before LLM quota check",
        )

    risk_preference = state.get("risk_preference", "balanced")

    messages = _build_stock_analysis_messages(
        symbol=market_snapshot.symbol,
        market=market_snapshot.market,
        risk_preference=risk_preference,
        market_data=market_snapshot.model_dump(mode="json"),
        indicators=indicators.model_dump(mode="json"),
        user_profile_context=state.get("user_profile_context"),
        relevant_memories_context=state.get("relevant_memories_context"),
    )

    quota_allowed, quota_reason, estimated_tokens, estimated_cost = await _check_stock_analysis_ai_quota(
        user_id=user_id,
        messages=messages,
    )

    if not quota_allowed:
        await _record_stock_analysis_ai_blocked(
            user_id=user_id,
            state=state,
            reason=quota_reason or "AI quota is not enough",
            estimated_tokens=estimated_tokens,
            estimated_cost=estimated_cost,
        )
        return _build_ai_quota_blocked_result_state(
            state=state,
            reason=quota_reason or "AI quota is not enough",
            estimated_tokens=estimated_tokens,
            estimated_cost=estimated_cost,
        )

    started_at = datetime.now(UTC)
    response = None

    try:
        llm = get_chat_model()
        response = await llm.ainvoke(messages)
        result = _parse_stock_analysis_result(response.content)
    except Exception as exc:
        logger.exception("stock analysis async llm node failed")
        await _record_stock_analysis_ai_failed(
            user_id=user_id,
            state=state,
            response=response,
            messages=messages,
            error_message=_safe_exception_message(exc),
            started_at=started_at,
        )
        return _build_llm_error_result_state(
            state=state,
            reason=_safe_exception_message(exc),
        )

    usage_log = await _record_stock_analysis_ai_success(
        user_id=user_id,
        state=state,
        response=response,
        messages=messages,
        completion_text=str(response.content),
        started_at=started_at,
    )

    metadata = {
        **state.get("metadata", {}),
        "ai_usage": {
            "feature": STOCK_ANALYSIS_AI_FEATURE,
            "status": "success",
            "usage_log_id": getattr(usage_log, "id", None),
            "model_name": get_settings().llm_model,
        },
    }

    return {
        "result": result,
        "metadata": metadata,
        "ai_quota_allowed": True,
        "ai_usage_log_id": getattr(usage_log, "id", None),
    }

async def _check_stock_analysis_ai_quota(
    *,
    user_id: int,
    messages: list[SystemMessage | HumanMessage],
) -> tuple[bool, str | None, AIUsageTokenEstimate, AIUsageCostEstimate]:
    """在调用 DeepSeek 前预估 token 和成本，并检查当前用户额度。"""

    token_service = AIUsageTokenService()
    settings = get_settings()

    prompt_estimate = token_service.estimate_prompt_tokens_from_messages(messages)
    estimated_tokens = AIUsageTokenEstimate(
        prompt_tokens=prompt_estimate.prompt_tokens,
        completion_tokens=STOCK_ANALYSIS_ESTIMATED_COMPLETION_TOKENS,
        total_tokens=prompt_estimate.prompt_tokens + STOCK_ANALYSIS_ESTIMATED_COMPLETION_TOKENS,
        token_source="estimated",
    )
    estimated_cost = token_service.estimate_cost(
        model_name=settings.llm_model,
        prompt_tokens=estimated_tokens.prompt_tokens,
        completion_tokens=estimated_tokens.completion_tokens,
    )

    async with AsyncSessionLocal() as db:
        repo = AsyncAIUsageRepository(db)
        quota_service = AIQuotaService(repo)

        result = await quota_service.check_quota(
            AIQuotaCheckRequest(
                user_id=user_id,
                feature=STOCK_ANALYSIS_AI_FEATURE,
                provider="deepseek",
                model_name=settings.llm_model,
                estimated_prompt_tokens=estimated_tokens.prompt_tokens,
                estimated_completion_tokens=estimated_tokens.completion_tokens,
                estimated_total_tokens=estimated_tokens.total_tokens,
                estimated_cost=estimated_cost.estimated_cost,
                currency=estimated_cost.currency,
            )
        )

    return result.allowed, result.reason, estimated_tokens, estimated_cost


async def _record_stock_analysis_ai_success(
    *,
    user_id: int,
    state: StockAnalysisState,
    response: Any,
    messages: list[SystemMessage | HumanMessage],
    completion_text: str,
    started_at: datetime,
):
    """记录主分析 LLM 成功调用，用于额度、成本和审计。

    记录失败只写日志，不影响已经生成的分析结果返回给用户。
    """

    try:
        async with AsyncSessionLocal() as db:
            repo = AsyncAIUsageRepository(db)
            usage_service = AIUsageService(repo)

            return await usage_service.record_success(
                user_id=user_id,
                feature=STOCK_ANALYSIS_AI_FEATURE,
                model_name=get_settings().llm_model,
                response=response,
                prompt_messages=messages,
                completion_text=completion_text,
                analysis_thread_id=state.get("thread_id"),
                started_at=started_at,
                finished_at=datetime.now(UTC),
                extra={
                    "symbol": state.get("symbol"),
                    "market": state.get("market"),
                    "graph_route": state.get("graph_route"),
                    "source": "stock_analysis_graph",
                },
            )
    except Exception:
        logger.exception("record stock analysis ai success usage failed")
        return None


async def _record_stock_analysis_ai_failed(
    *,
    user_id: int,
    state: StockAnalysisState,
    response: Any | None,
    messages: list[SystemMessage | HumanMessage],
    error_message: str,
    started_at: datetime,
) -> None:
    """记录主分析 LLM 调用失败。

    失败记录用于后续排查模型、网络或解析问题；图本身会返回降级结果。
    """

    try:
        async with AsyncSessionLocal() as db:
            repo = AsyncAIUsageRepository(db)
            usage_service = AIUsageService(repo)

            await usage_service.record_failed(
                user_id=user_id,
                feature=STOCK_ANALYSIS_AI_FEATURE,
                model_name=get_settings().llm_model,
                error_message=error_message,
                response=response,
                prompt_messages=messages,
                completion_text=str(getattr(response, "content", "") or ""),
                analysis_thread_id=state.get("thread_id"),
                started_at=started_at,
                finished_at=datetime.now(UTC),
                extra={
                    "symbol": state.get("symbol"),
                    "market": state.get("market"),
                    "graph_route": state.get("graph_route"),
                    "source": "stock_analysis_graph",
                },
            )
    except Exception:
        logger.exception("record stock analysis ai failed usage failed")


async def _record_stock_analysis_ai_blocked(
    *,
    user_id: int,
    state: StockAnalysisState,
    reason: str,
    estimated_tokens: AIUsageTokenEstimate,
    estimated_cost: AIUsageCostEstimate,
) -> None:
    """记录额度不足导致的 blocked 调用。"""

    try:
        async with AsyncSessionLocal() as db:
            repo = AsyncAIUsageRepository(db)
            usage_service = AIUsageService(repo)

            await usage_service.record_blocked(
                user_id=user_id,
                feature=STOCK_ANALYSIS_AI_FEATURE,
                model_name=get_settings().llm_model,
                reason=reason,
                estimated_prompt_tokens=estimated_tokens.prompt_tokens,
                estimated_completion_tokens=estimated_tokens.completion_tokens,
                estimated_cost=estimated_cost.estimated_cost,
                analysis_thread_id=state.get("thread_id"),
                extra={
                    "symbol": state.get("symbol"),
                    "market": state.get("market"),
                    "graph_route": state.get("graph_route"),
                    "source": "stock_analysis_graph",
                },
            )
    except Exception:
        logger.exception("record stock analysis ai blocked usage failed")


def _build_ai_quota_blocked_result_state(
    *,
    state: StockAnalysisState,
    reason: str,
    estimated_tokens: AIUsageTokenEstimate,
    estimated_cost: AIUsageCostEstimate,
) -> StockAnalysisState:
    """构造 AI 额度不足时的用户可读结果。

    额度不足时不调用 DeepSeek，也不会生成伪分析，只返回明确的安全提示。
    """

    message_service = AIQuotaMessageService()

    metadata = {
        **state.get("metadata", {}),
        "ai_quota": {
            "allowed": False,
            "reason": reason,
            "feature": STOCK_ANALYSIS_AI_FEATURE,
            "estimated_prompt_tokens": estimated_tokens.prompt_tokens,
            "estimated_completion_tokens": estimated_tokens.completion_tokens,
            "estimated_total_tokens": estimated_tokens.total_tokens,
            "estimated_cost": str(estimated_cost.estimated_cost),
            "currency": estimated_cost.currency,
        },
    }

    quality_context = state.get("quality_context")
    if quality_context is not None:
        quality_context = quality_context.model_copy(
            update={
                "graph_route": "quota_blocked",
                "route_reason": reason,
                "warnings": _deduplicate_messages(
                    [
                        *quality_context.warnings,
                        "AI 调用额度不足，本次没有继续调用 DeepSeek。",
                    ]
                ),
                "errors": _deduplicate_messages(
                    [
                        *quality_context.errors,
                        reason,
                    ]
                ),
            },
            deep=True,
        )

    result = StockAnalysisResult(
        summary=message_service.build_stock_analysis_blocked_summary(reason),
        risk_level="medium",
        trend="neutral",
        key_points=message_service.build_stock_analysis_blocked_key_points(reason),
        suggestion=message_service.build_stock_analysis_blocked_suggestion(),
        warnings=message_service.build_stock_analysis_blocked_warnings(),
    )

    return {
        "graph_route": "quota_blocked",
        "quality_context": quality_context,
        "route_reason": reason,
        "error_message": reason,
        "result": result,
        "metadata": metadata,
        "ai_quota_allowed": False,
        "ai_quota_reason": reason,
    }


def _build_llm_error_result_state(
    *,
    state: StockAnalysisState,
    reason: str,
) -> StockAnalysisState:
    """构造 LLM 异常时的安全降级结果。

    这里会保留错误原因供日志和审计使用，但用户侧只看到谨慎的降级分析。
    """

    metadata = {
        **state.get("metadata", {}),
        "llm_error_analysis": {
            "enabled": True,
            "reason": reason,
        },
    }

    quality_context = state.get("quality_context")
    if quality_context is not None:
        quality_context = quality_context.model_copy(
            update={
                "graph_route": "error",
                "route_reason": reason,
                "warnings": _deduplicate_messages(
                    [
                        *quality_context.warnings,
                        "AI 分析服务暂时不可用，本次返回系统降级结果。",
                    ]
                ),
                "errors": _deduplicate_messages(
                    [
                        *quality_context.errors,
                        reason,
                    ]
                ),
            },
            deep=True,
        )

    result = StockAnalysisResult(
        summary="AI 分析服务暂时不可用，系统已返回降级分析结果。",
        risk_level="medium",
        trend="neutral",
        key_points=[
            "系统已获取到基础分析上下文，但 AI 生成过程出现异常。",
            "为避免误导用户，本次不输出强趋势判断。",
        ],
        suggestion="建议稍后重新发起分析，或先查看行情、技术指标和数据质量报告。",
        warnings=[
            "本次结果由系统降级逻辑生成，不代表完整 AI 分析结论。",
            "该结果不构成投资建议。",
        ],
    )

    return {
        "graph_route": "error",
        "quality_context": quality_context,
        "route_reason": reason,
        "error_message": reason,
        "result": result,
        "metadata": metadata,
    }


def _safe_exception_message(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        message = exc.__class__.__name__

    return f"{exc.__class__.__name__}: {message[:300]}"


def _build_stock_analysis_messages(
    symbol: str,
    market: str,
    risk_preference: str,
    market_data: dict,
    indicators: dict,
    user_profile_context: dict[str, Any] | None = None,
    relevant_memories_context: dict[str, Any] | None = None,
) -> list[SystemMessage | HumanMessage]:
    """构造主分析 Prompt。

    Prompt 明确要求模型只基于后端提供的上下文回答：
    不编造新闻、财报、实时行情和外部事实，也不能承诺收益或命令用户交易。
    """

    system_prompt = """
    你是一名谨慎、客观的股票分析助手，服务对象是中文用户。
    
    重要规则：
    1. 只能根据输入数据分析，不要编造新闻、财报、实时行情或外部事实。
    2. 不要声称这是实时行情数据。
    3. 不要承诺收益，不要使用“必涨”“稳赚”“一定买入”等表达。
    4. 不要直接命令用户买入或卖出，只能给出观察性、研究性建议。
    5. 必须只返回 JSON，不要使用 markdown，不要添加额外解释。
    6. JSON 字段名必须使用英文，字段内容必须使用简体中文。
    7. risk_level 只能是 "low"、"medium"、"high"。
    8. trend 只能是 "bullish"、"bearish"、"neutral"。
    9. 所有 JSON 字段都必须出现，无法明确判断时 trend 使用 "neutral"，risk_level 使用 "medium"，列表字段使用 []。
    10. 如果提供了用户画像上下文，可以用它调整解释重点和表达风格，但不能把画像当成投资结论。
    11. 用户画像只能用于辅助说明风险偏好、关注点和表达方式，不得据此承诺收益或直接推荐买卖。
    12. 如果用户画像为空或证据不足，请按普通分析处理，不要编造用户偏好。
    13. 如果提供了相似记忆上下文，可以参考它理解用户过去关注的风险点、研究习惯和表达偏好。
    14. 相似记忆不是行情事实，不得把相似记忆当作新闻、财报、价格或技术指标依据。
    15. 相似记忆只能帮助调整解释重点，不能作为买入、卖出或预测收益的依据。
    """.strip()

    human_prompt = f"""
    请根据下面的股票信息、用户风险偏好、行情数据和基础指标，生成一份个股基础分析。
    
    JSON 必须符合下面结构：
    {{
      "summary": "简短中文总结",
      "risk_level": "low | medium | high",
      "trend": "bullish | bearish | neutral",
      "key_points": ["中文要点 1", "中文要点 2"],
      "suggestion": "中文研究性建议",
      "warnings": ["中文风险提示 1", "中文风险提示 2"]
    }}
    
    股票信息：
    symbol={symbol}
    market={market}
    
    用户风险偏好：
    {risk_preference}
    
    用户画像上下文：
    {json.dumps(user_profile_context or {"available": False}, ensure_ascii=False)}
    
    相似记忆上下文：
    {json.dumps(relevant_memories_context or {"available": False}, ensure_ascii=False)}
    
    行情数据：
    {json.dumps(market_data, ensure_ascii=False)}
    
    基础指标：
    {json.dumps(indicators, ensure_ascii=False)}
    """.strip()

    return [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ]


def _parse_stock_analysis_result(content: str) -> StockAnalysisResult:
    cleaned_content = content.strip()

    if cleaned_content.startswith("```"):
        cleaned_content = _strip_markdown_code_block(cleaned_content)

    try:
        payload = json.loads(cleaned_content)
    except json.JSONDecodeError as exc:
        raise BadRequestException(message="llm returned invalid json") from exc

    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        payload = payload["result"]

    if not isinstance(payload, dict):
        raise BadRequestException(message="llm returned invalid payload")

    return StockAnalysisResult.model_validate(
        _normalize_stock_analysis_payload(payload)
    )


def _normalize_stock_analysis_payload(payload: dict) -> dict:
    """Keep LLM format drift from becoming a 500 response."""
    warnings = _normalize_string_list(payload.get("warnings"))

    return {
        "summary": str(payload.get("summary") or "暂未生成明确摘要。"),
        "risk_level": _normalize_risk_level(payload.get("risk_level")),
        "trend": _normalize_trend(payload.get("trend")),
        "key_points": _normalize_string_list(payload.get("key_points")),
        "suggestion": str(payload.get("suggestion") or "建议结合更多信息谨慎观察。"),
        "warnings": warnings
        or ["当前分析基于模拟行情数据，不构成投资建议。"],
    }


def _normalize_risk_level(value: object) -> str:
    normalized = str(value or "").strip().lower()
    mapping = {
        "low": "low",
        "medium": "medium",
        "high": "high",
        "低": "low",
        "低风险": "low",
        "中": "medium",
        "中等": "medium",
        "中风险": "medium",
        "中等风险": "medium",
        "高": "high",
        "高风险": "high",
    }
    return mapping.get(normalized, "medium")


def _normalize_trend(value: object) -> str:
    normalized = str(value or "").strip().lower()
    mapping = {
        "bullish": "bullish",
        "bearish": "bearish",
        "neutral": "neutral",
        "看涨": "bullish",
        "偏多": "bullish",
        "多头": "bullish",
        "上涨": "bullish",
        "看跌": "bearish",
        "偏空": "bearish",
        "空头": "bearish",
        "下跌": "bearish",
        "中性": "neutral",
        "震荡": "neutral",
        "观望": "neutral",
    }
    return mapping.get(normalized, "neutral")


def _normalize_string_list(
    value: object,
    *,
    max_items: int = 8,
    max_length: int = 300,
) -> list[str]:
    if value is None:
        return []

    if isinstance(value, list):
        items = value
    else:
        items = [value]

    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text:
            continue

        result.append(text[:max_length])

        if len(result) >= max_items:
            break

    return result


def _strip_markdown_code_block(content: str) -> str:
    lines = content.splitlines()

    if lines and lines[0].startswith("```"):
        lines = lines[1:]

    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]

    return "\n".join(lines).strip()

