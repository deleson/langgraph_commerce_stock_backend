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
from app.schemas.stock_analysis_react import ReactToolCall

logger = logging.getLogger(__name__)


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

    try:
        llm = get_chat_model()
        response = await llm.ainvoke(messages)
        decision = _parse_agent_reason_decision(str(response.content))
    except Exception as exc:
        logger.exception("react agent reason node failed")
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
                },
            },
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
            },
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
            },
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
7. 如果用户问数据是否可靠、数据是否足够、是否过旧，优先考虑 get_data_quality。
8. 如果用户问是否适合自己、风险偏好、提醒设置，优先考虑 get_user_preference。
9. 如果用户问自选股、关注列表、列表内比较，优先考虑 get_watchlist。
10. 如果已有 observations 足够回答，就选择 final_answer。
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