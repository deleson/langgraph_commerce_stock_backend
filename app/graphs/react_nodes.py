import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from app.core.llm import get_chat_model
from app.graphs.react_states import StockAnalysisReactState
from app.graphs.react_tools import (
    format_react_tool_descriptions,
    get_default_react_tools,
    is_react_tool_allowed,
)
from datetime import UTC, datetime
from time import perf_counter
from typing import TYPE_CHECKING

from app.schemas.stock_analysis_react import (
    ReactObservation,
    ReactToolCall,
    ReactToolTrace,
)
from app.graphs.react_safety import (
    MAX_DATA_QUALITY_LIMIT,
    MAX_MARKET_OVERVIEW_LIMIT,
    MAX_REACT_FINAL_ANSWER_LENGTH,
    MAX_TECHNICAL_INDICATOR_LIMIT,
    MAX_WATCHLIST_LIMIT,
    clamp_int,
    safe_error_message,
    sanitize_tool_input,
    sanitize_tool_output,
    truncate_text,
)
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.repositories.ai_usage_repo import AsyncAIUsageRepository
from app.schemas.ai_usage import AIQuotaCheckRequest, AIUsageFeature
from app.services.ai_quota_service import AIQuotaService
from app.services.ai_usage_service import AIUsageService
from app.services.ai_usage_token_service import (
    AIUsageCostEstimate,
    AIUsageTokenEstimate,
    AIUsageTokenService,
)
from app.services.ai_quota_message_service import AIQuotaMessageService

if TYPE_CHECKING:
    from app.services.stock_analysis_react_tool_service import (
        StockAnalysisReactToolService,
    )

logger = logging.getLogger(__name__)

REACT_REASON_AI_FEATURE: AIUsageFeature = "react_reason"
REACT_FINAL_ANSWER_AI_FEATURE: AIUsageFeature = "react_final_answer"

REACT_REASON_ESTIMATED_COMPLETION_TOKENS = 500
REACT_FINAL_ANSWER_ESTIMATED_COMPLETION_TOKENS = 1200

async def agent_reason_node(
    state: StockAnalysisReactState,
) -> StockAnalysisReactState:
    """Ask the LLM to choose the next ReAct action.

    This node only decides what to do next.
    It does not execute tools.
    """

    allowed_tools = state.get("allowed_tools") or get_default_react_tools()
    observations = state.get("observations", [])
    iteration_count = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 3)

    if iteration_count >= max_iterations:
        return {
            "next_action": "final_answer",
            "final_answer": _build_iteration_limit_answer(state),
            "metadata": {
                **state.get("metadata", {}),
                "react_reason": {
                    "stopped_by": "max_iterations",
                    "iteration_count": iteration_count,
                    "max_iterations": max_iterations,
                },
            },
        }

    messages = _build_agent_reason_messages(
        state=state,
        allowed_tools=allowed_tools,
    )

    user_id = _get_required_int(state, "user_id")

    quota_allowed, quota_reason, estimated_tokens, estimated_cost = await _check_react_ai_quota(
        user_id=user_id,
        feature=REACT_REASON_AI_FEATURE,
        messages=messages,
        estimated_completion_tokens=REACT_REASON_ESTIMATED_COMPLETION_TOKENS,
    )

    if not quota_allowed:
        await _record_react_ai_blocked(
            user_id=user_id,
            state=state,
            feature=REACT_REASON_AI_FEATURE,
            reason=quota_reason or "AI quota is not enough",
            estimated_tokens=estimated_tokens,
            estimated_cost=estimated_cost,
        )

        return {
            "allowed_tools": allowed_tools,
            "next_action": "final_answer",
            "final_answer": _build_react_quota_blocked_answer(
                quota_reason or "AI quota is not enough",
                feature=REACT_REASON_AI_FEATURE,
            ),
            "ai_quota_allowed": False,
            "ai_quota_reason": quota_reason,
            "metadata": {
                **state.get("metadata", {}),
                "react_reason_ai_quota": {
                    "allowed": False,
                    "reason": quota_reason,
                    "feature": REACT_REASON_AI_FEATURE,
                    "estimated_prompt_tokens": estimated_tokens.prompt_tokens,
                    "estimated_completion_tokens": estimated_tokens.completion_tokens,
                    "estimated_total_tokens": estimated_tokens.total_tokens,
                    "estimated_cost": str(estimated_cost.estimated_cost),
                    "currency": estimated_cost.currency,
                },
            },
        }

    started_at = datetime.now(UTC)
    response = None
    usage_log = None

    try:
        llm = get_chat_model()
        response = await llm.ainvoke(messages)
        decision = _parse_agent_reason_decision(str(response.content))
        usage_log = await _record_react_ai_success(
            user_id=user_id,
            state=state,
            feature=REACT_REASON_AI_FEATURE,
            response=response,
            messages=messages,
            completion_text=str(response.content),
            started_at=started_at,
        )
    except Exception as exc:
        logger.exception("react agent reason node failed")
        await _record_react_ai_failed(
            user_id=user_id,
            state=state,
            feature=REACT_REASON_AI_FEATURE,
            response=response,
            messages=messages,
            error_message=_safe_exception_message(exc),
            started_at=started_at,
        )
        return _build_agent_reason_error_state(exc)

    next_action = decision.get("next_action")

    if next_action == "tool_call":
        tool_call_payload = decision.get("tool_call") or {}

        try:
            tool_call = ReactToolCall.model_validate(tool_call_payload)
        except ValidationError as exc:
            logger.exception("react tool call validation failed")
            return _build_agent_reason_error_state(exc)

        if not is_react_tool_allowed(tool_call.tool_name, allowed_tools):
            return {
                "next_action": "error",
                "error_message": f"tool is not allowed: {tool_call.tool_name}",
            }

        return {
            "allowed_tools": allowed_tools,
            "next_action": "tool_call",
            "tool_call": tool_call,
            "metadata": {
                **state.get("metadata", {}),
                "react_reason": {
                    "iteration_count": iteration_count,
                    "selected_tool": tool_call.tool_name,
                    "reason": tool_call.reason,
                    "observation_count": len(observations),
                    "usage_log_id": getattr(usage_log, "id", None),
                },
            },
            "ai_quota_allowed": True,
            "ai_usage_log_ids": [getattr(usage_log, "id")] if usage_log is not None else [],

        }

    if next_action == "final_answer":
        answer = str(decision.get("final_answer") or "").strip()
        if not answer:
            answer = "当前上下文不足以继续调用工具，我只能给出谨慎的阶段性回答。"

        return {
            "allowed_tools": allowed_tools,
            "next_action": "final_answer",
            "final_answer": answer,
            "metadata": {
                **state.get("metadata", {}),
                "react_reason": {
                    "iteration_count": iteration_count,
                    "selected_action": "final_answer",
                    "observation_count": len(observations),
                },
                "usage_log_id": getattr(usage_log, "id", None),
            },
            "ai_quota_allowed": True,
            "ai_usage_log_ids": [getattr(usage_log, "id")] if usage_log is not None else [],

        }

    if next_action == "error":
        return {
            "allowed_tools": allowed_tools,
            "next_action": "error",
            "error_message": str(
                decision.get("error_message") or "react agent returned error"
            ).strip(),
            "metadata": {
                **state.get("metadata", {}),
                "react_reason": {
                    "iteration_count": iteration_count,
                    "selected_action": "error",
                    "observation_count": len(observations),
                },
                "usage_log_id": getattr(usage_log, "id", None),
            },
            "ai_quota_allowed": True,
            "ai_usage_log_ids": [getattr(usage_log, "id")] if usage_log is not None else [],
        }

    return {
        "next_action": "error",
        "error_message": f"invalid next_action: {next_action}",
    }


def _build_agent_reason_messages(
    *,
    state: StockAnalysisReactState,
    allowed_tools: list[str],
) -> list[SystemMessage | HumanMessage]:
    tool_descriptions = format_react_tool_descriptions(allowed_tools)
    compact_state = _build_compact_reason_context(state)

    system_prompt = """
你是一个谨慎、客观的中文股票分析 ReAct Agent。

你的任务不是直接分析股票，而是决定下一步动作。

你只能输出 JSON，不能输出 markdown，不能输出额外解释。

你有三种动作：
1. tool_call：需要调用一个工具获取更多信息。
2. final_answer：已有信息足够，可以最终回答用户。
3. error：无法继续。

重要规则：
1. 只能从 allowed_tools 中选择工具。
2. 不要编造行情、技术指标、用户偏好或自选股。
3. 不要承诺收益，不要使用“必涨”“稳赚”“一定买入”等表达。
4. 如果缺少原始分析记录，优先调用 get_analysis_record。
5. 如果用户问当前行情、价格、K线、数据来源，优先考虑 get_market_overview。
6. 如果用户问 MA、RSI、MACD、波动率、动量、成交量，优先考虑 get_technical_indicators。
7. 如果用户问数据是否可靠、数据是否足够、是否过时，优先考虑 get_data_quality。
8. 如果用户问历史回测、策略历史表现、最大回撤、胜率、夏普比率、是否跑赢买入持有，优先考虑 get_backtest_result。
9. 调用 get_backtest_result 必须提供 start_date 和 end_date；如果用户没有给明确回测区间，应先选择 final_answer 追问用户回测时间范围，不要自己猜。
10. 如果用户问是否适合自己、风险偏好、提醒设置，优先考虑 get_user_preference。
11. 如果用户只是想查看自选股、关注列表内容，优先考虑 get_watchlist。
12. 如果用户问“自选股里哪些更值得研究”“自选股候选排名”“关注列表里谁评分更高”，优先考虑 get_stock_candidates，并使用 universe_source=watchlist。
13. 如果用户明确给出多个股票代码，并问“谁更值得研究”“帮我对比候选评分”“这些里面谁更好”，优先考虑 get_stock_candidates，并使用 universe_source=manual，同时传入 symbols。
14. 如果用户要求“推荐股票”“帮我找几只股票”，但没有提供股票池，也没有明确使用自选股，应选择 final_answer 追问用户：使用自选股还是手动提供股票列表。不要自己编造股票，不要做全市场扫描。
15. get_stock_candidates 只能输出研究线索和候选评分，不是买卖建议；如果用户要求直接告诉他买哪只，应选择 final_answer 做风险边界说明，并引导为候选研究。
16. 如果已有 get_stock_candidates 的 observation 且足够回答用户问题，就选择 final_answer，不要重复调用同一个候选工具。
17. 如果已有 observations 足够回答，就选择 final_answer。
""".strip()

    human_prompt = f"""
用户追问：
{state.get("message", "")}

业务分析会话 ID：
{state.get("analysis_thread_id")}

已引用股票：
symbol={state.get("referenced_symbol")}
market={state.get("referenced_market")}

允许使用的工具：
{tool_descriptions}

当前上下文摘要：
{json.dumps(compact_state, ensure_ascii=False)}

请只返回 JSON，格式必须是以下三种之一：

调用工具：
{{
  "next_action": "tool_call",
  "tool_call": {{
    "tool_name": "get_analysis_record",
    "tool_input": {{}},
    "reason": "为什么需要调用这个工具"
  }}
}}

候选工具示例一：用户问“我的自选股里哪些更值得研究”
{{
  "next_action": "tool_call",
  "tool_call": {{
    "tool_name": "get_stock_candidates",
    "tool_input": {{
      "universe_source": "watchlist",
      "top_n": 5,
      "include_score_breakdown": true,
      "include_excluded": false
    }},
    "reason": "用户想从自己的自选股中筛选更值得研究的候选股票，需要调用候选评分工具。"
  }}
}}

候选工具示例二：用户问“AAPL、MSFT、NVDA 谁更值得研究”
{{
  "next_action": "tool_call",
  "tool_call": {{
    "tool_name": "get_stock_candidates",
    "tool_input": {{
      "universe_source": "manual",
      "symbols": [
        {{"symbol": "AAPL", "market": "US"}},
        {{"symbol": "MSFT", "market": "US"}},
        {{"symbol": "NVDA", "market": "US"}}
      ],
      "top_n": 5,
      "include_score_breakdown": true,
      "include_excluded": false
    }},
    "reason": "用户给出了明确股票池并要求比较候选评分，需要调用候选评分工具。"
  }}
}}

最终回答：
{{
  "next_action": "final_answer",
  "final_answer": "中文回答"
}}

错误：
{{
  "next_action": "error",
  "error_message": "错误原因"
}}
""".strip()

    return [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ]


def _build_compact_reason_context(
    state: StockAnalysisReactState,
) -> dict[str, Any]:
    observations = [
        _dump_observation(observation)
        for observation in state.get("observations", [])
    ]

    return {
        "analysis_thread_id": state.get("analysis_thread_id"),
        "user_id": state.get("user_id"),
        "referenced_analysis_record_id": state.get("referenced_analysis_record_id"),
        "referenced_symbol": state.get("referenced_symbol"),
        "referenced_market": state.get("referenced_market"),
        "has_context_snapshot": bool(state.get("context_snapshot")),
        "has_result_snapshot": bool(state.get("result_snapshot")),
        "iteration_count": state.get("iteration_count", 0),
        "max_iterations": state.get("max_iterations", 3),
        "observations": observations[-5:],
        "conversation_context": state.get("conversation_context") or {},
    }


def _dump_observation(
    observation: Any,
) -> dict[str, Any]:
    if hasattr(observation, "model_dump"):
        payload = observation.model_dump(mode="json")
    elif isinstance(observation, dict):
        payload = observation
    else:
        return {"value": str(observation)}

    tool_output = payload.get("tool_output")
    if isinstance(tool_output, dict):
        payload["tool_output"] = _truncate_dict(tool_output, max_items=20)

    return payload


def _truncate_dict(
    payload: dict[str, Any],
    *,
    max_items: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {}

    for index, (key, value) in enumerate(payload.items()):
        if index >= max_items:
            result["_truncated"] = True
            break
        result[key] = value

    return result


def _parse_agent_reason_decision(
    content: str,
) -> dict[str, Any]:
    cleaned_content = content.strip()

    if cleaned_content.startswith("```"):
        cleaned_content = _strip_markdown_code_block(cleaned_content)

    payload = json.loads(cleaned_content)

    if not isinstance(payload, dict):
        raise ValueError("react agent returned non-object json")

    return payload


def _strip_markdown_code_block(
    content: str,
) -> str:
    lines = content.splitlines()

    if lines and lines[0].startswith("```"):
        lines = lines[1:]

    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]

    return "\n".join(lines).strip()


def _build_agent_reason_error_state(
    exc: Exception,
) -> StockAnalysisReactState:
    return {
        "next_action": "error",
        "error_message": _safe_exception_message(exc),
    }


def _safe_exception_message(
    exc: Exception,
) -> str:
    message = str(exc).strip()
    if not message:
        message = exc.__class__.__name__

    return f"{exc.__class__.__name__}: {message[:300]}"


def _build_iteration_limit_answer(
    state: StockAnalysisReactState,
) -> str:
    return (
        "我已经完成当前允许范围内的工具检查。"
        "由于达到本次追问的最大推理轮数，下面只能基于已获得的信息给出谨慎回答。"
        "如果你需要更深入分析，可以重新发起一个更具体的问题。"
    )


def create_react_tool_execution_node(
    tool_service: "StockAnalysisReactToolService",
):
    """Create a ReAct tool execution node with request-scoped dependencies.

    The returned node can be registered into LangGraph.
    The database session stays inside tool_service, not inside graph state.
    """

    async def react_tool_execution_node(
        state: StockAnalysisReactState,
    ) -> StockAnalysisReactState:
        return await _execute_react_tool(
            state=state,
            tool_service=tool_service,
        )

    return react_tool_execution_node


async def _execute_react_tool(
    *,
    state: StockAnalysisReactState,
    tool_service: "StockAnalysisReactToolService",
) -> StockAnalysisReactState:
    tool_call = state.get("tool_call")

    if tool_call is None:
        return {
            "next_action": "error",
            "error_message": "tool_call is required before executing react tool",
        }

    tool_name = tool_call.tool_name
    tool_input = sanitize_tool_input(dict(tool_call.tool_input or {}))
    tool_reason = truncate_text(tool_call.reason or "", max_length=500)
    iteration_count = state.get("iteration_count", 0)

    start_time = perf_counter()

    try:
        observation = await _call_react_tool(
            tool_service=tool_service,
            state=state,
            tool_call=tool_call,
            tool_input=tool_input,
        )

        duration_ms = int((perf_counter() - start_time) * 1000)
        trace = ReactToolTrace(
            step=iteration_count + 1,
            action="tool_call",
            tool_name=tool_name,
            reason=tool_reason,
            duration_ms=duration_ms,
            success=True,
        )

        return _build_tool_execution_update(
            state=state,
            observation=observation,
            trace=trace,
        )

    except Exception as exc:
        logger.exception("react tool execution failed")

        duration_ms = int((perf_counter() - start_time) * 1000)
        error_message = safe_error_message(exc)

        observation = ReactObservation(
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=None,
            success=False,
            error_message=error_message,
            created_at=datetime.now(UTC),
        )
        trace = ReactToolTrace(
            step=iteration_count + 1,
            action="tool_call",
            tool_name=tool_name,
            reason=tool_reason,
            duration_ms=duration_ms,
            success=False,
            error_message=error_message,
        )

        return _build_tool_execution_update(
            state=state,
            observation=observation,
            trace=trace,
        )


async def _call_react_tool(
    *,
    tool_service: "StockAnalysisReactToolService",
    state: StockAnalysisReactState,
    tool_call: ReactToolCall,
    tool_input: dict[str, Any],
) -> ReactObservation:
    tool_name = tool_call.tool_name

    if tool_name == "get_analysis_record":
        return await tool_service.get_analysis_record(
            analysis_thread_id=str(
                tool_input.get("analysis_thread_id")
                or state.get("analysis_thread_id")
                or ""
            ),
            user_id=_get_required_int(state, "user_id"),
        )

    if tool_name == "get_market_overview":
        return await tool_service.get_market_overview(
            symbol=_get_symbol(tool_input, state),
            market=_get_market(tool_input, state),
            timeframe=tool_input.get("timeframe", "1d"),
            limit=clamp_int(
                tool_input.get("limit"),
                default=30,
                min_value=1,
                max_value=MAX_MARKET_OVERVIEW_LIMIT,
            ),
            include_technical_indicators=bool(
                tool_input.get("include_technical_indicators", False)
            ),
            include_data_quality=bool(tool_input.get("include_data_quality", True)),
            include_sync_status=bool(tool_input.get("include_sync_status", True)),
            technical_indicator_limit=clamp_int(
                tool_input.get("technical_indicator_limit"),
                default=120,
                min_value=20,
                max_value=MAX_TECHNICAL_INDICATOR_LIMIT,
            ),
            adjust_type=tool_input.get("adjust_type", "none"),
            source=tool_input.get("source"),
        )

    if tool_name == "get_technical_indicators":
        return await tool_service.get_technical_indicators(
            symbol=_get_symbol(tool_input, state),
            market=_get_market(tool_input, state),
            timeframe=tool_input.get("timeframe", "1d"),
            limit=clamp_int(
                tool_input.get("limit"),
                default=120,
                min_value=20,
                max_value=MAX_TECHNICAL_INDICATOR_LIMIT,
            ),
            adjust_type=tool_input.get("adjust_type", "none"),
            source=tool_input.get("source"),
        )

    if tool_name == "get_data_quality":
        return await tool_service.get_data_quality(
            symbol=_get_symbol(tool_input, state),
            market=_get_market(tool_input, state),
            timeframe=tool_input.get("timeframe", "1d"),
            limit=clamp_int(
                tool_input.get("limit"),
                default=120,
                min_value=1,
                max_value=MAX_DATA_QUALITY_LIMIT,
            ),
            adjust_type=tool_input.get("adjust_type", "none"),
            source=tool_input.get("source"),
            min_required=clamp_int(
                tool_input.get("min_required"),
                default=35,
                min_value=1,
                max_value=MAX_DATA_QUALITY_LIMIT,
            ),
            stale_after_days=tool_input.get("stale_after_days"),
        )

    if tool_name == "get_user_preference":
        return await tool_service.get_user_preference(
            user_id=_get_required_int(state, "user_id"),
        )

    if tool_name == "get_watchlist":
        return await tool_service.get_watchlist(
            user_id=_get_required_int(state, "user_id"),
            limit=clamp_int(
                tool_input.get("limit"),
                default=50,
                min_value=1,
                max_value=MAX_WATCHLIST_LIMIT,
            ),
        )

    if tool_name == "get_backtest_result":
        start_date = tool_input.get("start_date")
        end_date = tool_input.get("end_date")

        if not start_date or not end_date:
            raise ValueError(
                "start_date and end_date are required for get_backtest_result"
            )

        return await tool_service.get_backtest_result(
            symbol=_get_symbol(tool_input, state),
            market=_get_market(tool_input, state),
            start_date=start_date,
            end_date=end_date,
            initial_cash=tool_input.get("initial_cash", "100000"),
            position_size_ratio=float(
                tool_input.get("position_size_ratio") or 1.0
            ),
            timeframe=tool_input.get("timeframe", "1d"),
            adjust_type=tool_input.get("adjust_type", "none"),
            source=tool_input.get("source"),
            min_required_candles=clamp_int(
                tool_input.get("min_required_candles"),
                default=60,
                min_value=30,
                max_value=1000,
            ),
            enforce_data_quality=bool(
                tool_input.get("enforce_data_quality", True)
            ),
            data_quality_stale_after_days=tool_input.get(
                "data_quality_stale_after_days"
            ),
        )
    if tool_name == "get_stock_candidates":
        return await tool_service.get_stock_candidates(
            user_id=_get_required_int(state, "user_id"),
            universe_source=tool_input.get("universe_source", "watchlist"),
            symbols=tool_input.get("symbols") or [],
            top_n=clamp_int(
                tool_input.get("top_n"),
                default=5,
                min_value=1,
                max_value=10,
            ),
            market=tool_input.get("market"),
            timeframe=tool_input.get("timeframe", "1d"),
            limit=clamp_int(
                tool_input.get("limit"),
                default=120,
                min_value=30,
                max_value=300,
            ),
            min_required_candles=clamp_int(
                tool_input.get("min_required_candles"),
                default=60,
                min_value=30,
                max_value=300,
            ),
            adjust_type=tool_input.get("adjust_type", "none"),
            source=tool_input.get("source"),
            include_excluded=bool(tool_input.get("include_excluded", False)),
            include_score_breakdown=bool(
                tool_input.get("include_score_breakdown", True)
            ),
            include_ai_explanation=bool(
                tool_input.get("include_ai_explanation", False)
            ),
            explanation_style=tool_input.get("explanation_style", "balanced"),
            max_candidates_to_explain=clamp_int(
                tool_input.get("max_candidates_to_explain"),
                default=3,
                min_value=1,
                max_value=10,
            ),
            enforce_data_quality=bool(
                tool_input.get("enforce_data_quality", True)
            ),
            data_quality_stale_after_days=tool_input.get(
                "data_quality_stale_after_days"
            ),
        )

    raise ValueError(f"unsupported react tool: {tool_name}")


def _build_tool_execution_update(
    *,
    state: StockAnalysisReactState,
    observation: ReactObservation,
    trace: ReactToolTrace,
) -> StockAnalysisReactState:
    safe_observation = _sanitize_observation_for_state(observation)
    observation_count = len(state.get("observations", [])) + 1
    trace_count = len(state.get("trace", [])) + 1

    return {
        "observations": [safe_observation],
        "trace": [trace],
        "iteration_count": state.get("iteration_count", 0) + 1,
        "tool_call": None,
        "metadata": {
            **state.get("metadata", {}),
            "react_tool_execution": {
                "last_tool_name": safe_observation.tool_name,
                "last_tool_success": safe_observation.success,
                "observation_count": observation_count,
                "trace_count": trace_count,
            },
        },
    }


def _sanitize_observation_for_state(
    observation: ReactObservation,
) -> ReactObservation:
    payload = observation.model_dump(mode="python")
    payload["tool_input"] = sanitize_tool_input(payload.get("tool_input") or {})
    payload["tool_output"] = sanitize_tool_output(payload.get("tool_output"))
    payload["error_message"] = (
        truncate_text(payload["error_message"], max_length=500)
        if payload.get("error_message")
        else None
    )

    return ReactObservation.model_validate(payload)

def _get_symbol(
    tool_input: dict[str, Any],
    state: StockAnalysisReactState,
) -> str:
    symbol = tool_input.get("symbol") or state.get("referenced_symbol")
    if not symbol:
        raise ValueError("symbol is required for this react tool")

    return str(symbol).strip().upper()


def _get_market(
    tool_input: dict[str, Any],
    state: StockAnalysisReactState,
) -> str:
    market = tool_input.get("market") or state.get("referenced_market")
    if not market:
        raise ValueError("market is required for this react tool")

    return str(market).strip().upper()


def _get_required_int(
    state: StockAnalysisReactState,
    key: str,
) -> int:
    value = state.get(key)
    if value is None:
        raise ValueError(f"{key} is required")

    return int(value)


async def final_answer_node(
    state: StockAnalysisReactState,
) -> StockAnalysisReactState:
    """Build the final user-facing answer from ReAct context and observations.

    If a previous node already produced final_answer, this node keeps it.
    Otherwise it asks the LLM to summarize the available context.
    """

    existing_answer = truncate_text(
        str(state.get("final_answer") or "").strip(),
        max_length=MAX_REACT_FINAL_ANSWER_LENGTH,
    )
    if existing_answer:
        return {
            "next_action": "final_answer",
            "final_answer": existing_answer,
            "metadata": {
                **state.get("metadata", {}),
                "react_final_answer": {
                    "source": "existing_final_answer",
                    "observation_count": len(state.get("observations", [])),
                    "trace_count": len(state.get("trace", [])),
                },
            },
        }

    messages = _build_final_answer_messages(state)
    answer_source = "llm"

    user_id = _get_required_int(state, "user_id")

    quota_allowed, quota_reason, estimated_tokens, estimated_cost = await _check_react_ai_quota(
        user_id=user_id,
        feature=REACT_FINAL_ANSWER_AI_FEATURE,
        messages=messages,
        estimated_completion_tokens=REACT_FINAL_ANSWER_ESTIMATED_COMPLETION_TOKENS,
    )

    if not quota_allowed:
        await _record_react_ai_blocked(
            user_id=user_id,
            state=state,
            feature=REACT_FINAL_ANSWER_AI_FEATURE,
            reason=quota_reason or "AI quota is not enough",
            estimated_tokens=estimated_tokens,
            estimated_cost=estimated_cost,
        )

        return {
            "next_action": "final_answer",
            "final_answer": _build_react_quota_blocked_answer(
                quota_reason or "AI quota is not enough",
                feature=REACT_FINAL_ANSWER_AI_FEATURE,
            ),
            "ai_quota_allowed": False,
            "ai_quota_reason": quota_reason,
            "metadata": {
                **state.get("metadata", {}),
                "react_final_answer_ai_quota": {
                    "allowed": False,
                    "reason": quota_reason,
                    "feature": REACT_FINAL_ANSWER_AI_FEATURE,
                    "estimated_prompt_tokens": estimated_tokens.prompt_tokens,
                    "estimated_completion_tokens": estimated_tokens.completion_tokens,
                    "estimated_total_tokens": estimated_tokens.total_tokens,
                    "estimated_cost": str(estimated_cost.estimated_cost),
                    "currency": estimated_cost.currency,
                    "observation_count": len(state.get("observations", [])),
                    "trace_count": len(state.get("trace", [])),
                },
            },
        }

    started_at = datetime.now(UTC)
    response = None
    usage_log = None

    try:
        llm = get_chat_model()
        response = await llm.ainvoke(messages)
        answer = _normalize_final_answer(str(response.content))
        usage_log = await _record_react_ai_success(
            user_id=user_id,
            state=state,
            feature=REACT_FINAL_ANSWER_AI_FEATURE,
            response=response,
            messages=messages,
            completion_text=str(response.content),
            started_at=started_at,
        )
    except Exception as exc:
        logger.exception("react final answer node failed")
        await _record_react_ai_failed(
            user_id=user_id,
            state=state,
            feature=REACT_FINAL_ANSWER_AI_FEATURE,
            response=response,
            messages=messages,
            error_message=_safe_exception_message(exc),
            started_at=started_at,
        )
        answer_source = "fallback"
        answer = _build_final_answer_fallback(
            state=state,
            reason=_safe_exception_message(exc),
        )

    return {
        "next_action": "final_answer",
        "final_answer": answer,
        "ai_quota_allowed": True,
        "ai_usage_log_ids": [getattr(usage_log, "id")] if usage_log is not None else [],
        "metadata": {
            **state.get("metadata", {}),
            "react_final_answer": {
                "source": answer_source,
                "usage_log_id": getattr(usage_log, "id", None),
                "observation_count": len(state.get("observations", [])),
                "trace_count": len(state.get("trace", [])),
                "successful_observation_count": _count_observations(
                    state,
                    success=True,
                ),
                "failed_observation_count": _count_observations(
                    state,
                    success=False,
                ),
            },
        },
    }

async def _check_react_ai_quota(
    *,
    user_id: int,
    feature: AIUsageFeature,
    messages: list[SystemMessage | HumanMessage],
    estimated_completion_tokens: int,
) -> tuple[bool, str | None, AIUsageTokenEstimate, AIUsageCostEstimate]:
    token_service = AIUsageTokenService()
    settings = get_settings()

    prompt_estimate = token_service.estimate_prompt_tokens_from_messages(messages)
    estimated_tokens = AIUsageTokenEstimate(
        prompt_tokens=prompt_estimate.prompt_tokens,
        completion_tokens=estimated_completion_tokens,
        total_tokens=prompt_estimate.prompt_tokens + estimated_completion_tokens,
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
                feature=feature,
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

async def _record_react_ai_success(
    *,
    user_id: int,
    state: StockAnalysisReactState,
    feature: AIUsageFeature,
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
                feature=feature,
                model_name=get_settings().llm_model,
                response=response,
                prompt_messages=messages,
                completion_text=completion_text,
                analysis_thread_id=state.get("analysis_thread_id"),
                trace_id=state.get("react_graph_checkpoint_id"),
                started_at=started_at,
                finished_at=datetime.now(UTC),
                extra={
                    "source": "stock_analysis_react_graph",
                    "referenced_symbol": state.get("referenced_symbol"),
                    "referenced_market": state.get("referenced_market"),
                    "referenced_analysis_record_id": state.get("referenced_analysis_record_id"),
                    "iteration_count": state.get("iteration_count", 0),
                    "observation_count": len(state.get("observations", [])),
                },
            )
    except Exception:
        logger.exception("record react ai success usage failed")
        return None

async def _record_react_ai_failed(
    *,
    user_id: int,
    state: StockAnalysisReactState,
    feature: AIUsageFeature,
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
                feature=feature,
                model_name=get_settings().llm_model,
                error_message=error_message,
                response=response,
                prompt_messages=messages,
                completion_text=str(getattr(response, "content", "") or ""),
                analysis_thread_id=state.get("analysis_thread_id"),
                trace_id=state.get("react_graph_checkpoint_id"),
                started_at=started_at,
                finished_at=datetime.now(UTC),
                extra={
                    "source": "stock_analysis_react_graph",
                    "referenced_symbol": state.get("referenced_symbol"),
                    "referenced_market": state.get("referenced_market"),
                    "referenced_analysis_record_id": state.get("referenced_analysis_record_id"),
                    "iteration_count": state.get("iteration_count", 0),
                    "observation_count": len(state.get("observations", [])),
                },
            )
    except Exception:
        logger.exception("record react ai failed usage failed")

async def _record_react_ai_blocked(
    *,
    user_id: int,
    state: StockAnalysisReactState,
    feature: AIUsageFeature,
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
                feature=feature,
                model_name=get_settings().llm_model,
                reason=reason,
                estimated_prompt_tokens=estimated_tokens.prompt_tokens,
                estimated_completion_tokens=estimated_tokens.completion_tokens,
                estimated_cost=estimated_cost.estimated_cost,
                analysis_thread_id=state.get("analysis_thread_id"),
                trace_id=state.get("react_graph_checkpoint_id"),
                extra={
                    "source": "stock_analysis_react_graph",
                    "referenced_symbol": state.get("referenced_symbol"),
                    "referenced_market": state.get("referenced_market"),
                    "referenced_analysis_record_id": state.get("referenced_analysis_record_id"),
                    "iteration_count": state.get("iteration_count", 0),
                    "observation_count": len(state.get("observations", [])),
                },
            )
    except Exception:
        logger.exception("record react ai blocked usage failed")

def _build_react_quota_blocked_answer(
    reason: str,
    *,
    feature: AIUsageFeature,
) -> str:
    return AIQuotaMessageService().build_react_blocked_answer(
        feature=feature,
        reason=reason,
    )


def _build_final_answer_messages(
    state: StockAnalysisReactState,
) -> list[SystemMessage | HumanMessage]:
    context = _build_final_answer_context(state)

    system_prompt = """
你是一个谨慎、客观的中文股票分析助手。

你正在基于一次已有股票分析，以及 ReAct 工具调用结果，回答用户的追问。

重要规则：
1. 只能基于提供的上下文和工具观察结果回答。
2. 不要编造实时行情、新闻、财报或未提供的数据。
3. 不要承诺收益，不要说“必涨”“稳赚”“一定买入”。
4. 如果数据不足，要明确说明不确定性。
5. 使用简体中文回答。
6. 回答要适合普通用户理解，必要时可以分点说明。
7. 结尾要提醒：内容仅供研究参考，不构成投资建议。
""".strip()

    human_prompt = f"""
用户追问：
{state.get("message", "")}

当前 ReAct 上下文：
{json.dumps(context, ensure_ascii=False)}

请基于以上信息，生成最终中文回答。
""".strip()

    return [
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ]


def _build_final_answer_context(
    state: StockAnalysisReactState,
) -> dict[str, Any]:
    context_snapshot = state.get("context_snapshot") or {}
    result_snapshot = state.get("result_snapshot") or {}

    if isinstance(context_snapshot, dict):
        compact_context_snapshot = _truncate_dict(context_snapshot, max_items=30)
    else:
        compact_context_snapshot = {"value": str(context_snapshot)}

    if isinstance(result_snapshot, dict):
        compact_result_snapshot = _truncate_dict(result_snapshot, max_items=30)
    else:
        compact_result_snapshot = {"value": str(result_snapshot)}

    observations = [
        _dump_observation(observation)
        for observation in state.get("observations", [])
    ]

    trace = [
        _dump_trace_item(trace_item)
        for trace_item in state.get("trace", [])
    ]

    return {
        "analysis_thread_id": state.get("analysis_thread_id"),
        "user_id": state.get("user_id"),
        "referenced_analysis_record_id": state.get("referenced_analysis_record_id"),
        "referenced_symbol": state.get("referenced_symbol"),
        "referenced_market": state.get("referenced_market"),
        "context_snapshot": compact_context_snapshot,
        "result_snapshot": compact_result_snapshot,
        "observations": observations[-8:],
        "trace": trace[-8:],
        "iteration_count": state.get("iteration_count", 0),
        "max_iterations": state.get("max_iterations", 3),
        "conversation_context": state.get("conversation_context") or {},
    }


def _dump_trace_item(
    trace_item: Any,
) -> dict[str, Any]:
    if hasattr(trace_item, "model_dump"):
        return trace_item.model_dump(mode="json")

    if isinstance(trace_item, dict):
        return trace_item

    return {"value": str(trace_item)}


def _normalize_final_answer(
    content: str,
) -> str:
    answer = content.strip()

    if answer.startswith("```"):
        answer = _strip_markdown_code_block(answer)

    if not answer:
        return "当前可用信息不足，我暂时无法生成可靠的追问回答。"

    return truncate_text(
        answer,
        max_length=MAX_REACT_FINAL_ANSWER_LENGTH,
    )


def _build_final_answer_fallback(
    *,
    state: StockAnalysisReactState,
    reason: str,
) -> str:
    symbol = state.get("referenced_symbol") or "该股票"
    market = state.get("referenced_market") or "当前市场"
    success_count = _count_observations(state, success=True)
    failed_count = _count_observations(state, success=False)

    if success_count > 0:
        return (
            f"我已经读取到 {symbol}（{market}）的部分工具结果，"
            "但在整理最终回答时出现了模型调用异常。"
            f"当前成功获取了 {success_count} 条观察结果，"
            f"失败 {failed_count} 条。"
            "建议你稍后重新追问，或换一个更具体的问题继续分析。"
            "以上内容仅供研究参考，不构成投资建议。"
        )

    return (
        f"我暂时无法基于 {symbol}（{market}）生成可靠的追问回答。"
        f"原因是最终回答生成失败：{reason}。"
        "建议先确认该股票是否已有分析记录、行情数据和技术指标数据。"
        "以上内容仅供研究参考，不构成投资建议。"
    )


def _count_observations(
    state: StockAnalysisReactState,
    *,
    success: bool,
) -> int:
    count = 0

    for observation in state.get("observations", []):
        if hasattr(observation, "success"):
            if observation.success is success:
                count += 1
            continue

        if isinstance(observation, dict) and observation.get("success") is success:
            count += 1

    return count