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
    market_snapshot = state.get("market_snapshot")

    if market_snapshot is None:
        raise BadRequestException(message="market_snapshot is required")

    indicators = IndicatorService().calculate(market_snapshot)

    return {
        "indicators": indicators,
    }


def load_technical_indicators_node(state: StockAnalysisState) -> StockAnalysisState:
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
) -> list[SystemMessage | HumanMessage]:
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

