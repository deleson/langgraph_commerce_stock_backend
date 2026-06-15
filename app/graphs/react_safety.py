"""ReAct 工具输入输出的安全裁剪工具。

ReAct Observation 会回流给 LLM，如果不限制长度和嵌套深度，
一次工具调用可能把过大的行情、回测或候选结果塞进上下文，导致成本失控或响应过慢。
本文件只做数据裁剪和格式安全处理，不改变业务含义。
"""

from typing import Any


MAX_REACT_STRING_LENGTH = 1200
MAX_REACT_ERROR_LENGTH = 500
MAX_REACT_DICT_ITEMS = 30
MAX_REACT_LIST_ITEMS = 30
MAX_REACT_NESTING_DEPTH = 3
MAX_REACT_FINAL_ANSWER_LENGTH = 3000

MAX_MARKET_OVERVIEW_LIMIT = 60
MAX_TECHNICAL_INDICATOR_LIMIT = 200
MAX_DATA_QUALITY_LIMIT = 200
MAX_WATCHLIST_LIMIT = 50

MAX_CONVERSATION_CONTENT_LENGTH = 3000
MAX_CONVERSATION_TOOL_CONTENT_LENGTH = 1000
MAX_CONVERSATION_CONTEXT_MESSAGES = 10
MAX_CONVERSATION_CONTEXT_MESSAGES_MAX = 20
MAX_CONVERSATION_TRACE_REASON_LENGTH = 500

def clamp_int(
    value: Any,
    *,
    default: int,
    min_value: int,
    max_value: int,
) -> int:
    """把外部输入限制在指定整数范围内。"""

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    return max(min_value, min(parsed, max_value))


def truncate_text(
    value: Any,
    *,
    max_length: int = MAX_REACT_STRING_LENGTH,
) -> str:
    """截断过长文本，避免 Observation 或错误信息撑爆上下文。"""

    text = str(value)

    if len(text) <= max_length:
        return text

    return f"{text[:max_length]}...[truncated]"


def safe_error_message(
    exc: Exception,
) -> str:
    """把异常转成可记录、可返回的安全短消息。"""

    message = str(exc).strip() or exc.__class__.__name__
    return truncate_text(
        f"{exc.__class__.__name__}: {message}",
        max_length=MAX_REACT_ERROR_LENGTH,
    )


def sanitize_for_react(
    value: Any,
    *,
    depth: int = 0,
) -> Any:
    """递归裁剪 ReAct 上下文。

    dict / list / Pydantic Model 都会被限制长度、数量和嵌套深度。
    """

    if depth >= MAX_REACT_NESTING_DEPTH:
        return truncate_text(value)

    if value is None or isinstance(value, bool | int | float):
        return value

    if isinstance(value, str):
        return truncate_text(value)

    if isinstance(value, dict):
        result: dict[str, Any] = {}

        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_REACT_DICT_ITEMS:
                result["_truncated"] = True
                break

            result[str(key)] = sanitize_for_react(
                item,
                depth=depth + 1,
            )

        return result

    if isinstance(value, list | tuple):
        result = [
            sanitize_for_react(item, depth=depth + 1)
            for item in value[:MAX_REACT_LIST_ITEMS]
        ]

        if len(value) > MAX_REACT_LIST_ITEMS:
            result.append("[truncated]")

        return result

    if hasattr(value, "model_dump"):
        return sanitize_for_react(
            value.model_dump(mode="json"),
            depth=depth + 1,
        )

    return truncate_text(value)


def sanitize_tool_input(
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    """清洗工具输入，保证 tool_input 至少是 dict。"""

    payload = sanitize_for_react(tool_input)

    if isinstance(payload, dict):
        return payload

    return {}


def sanitize_tool_output(
    tool_output: Any,
) -> dict[str, Any] | list[Any] | str | None:
    """清洗工具输出，保证 Observation 中只保存有限大小的安全结构。"""

    payload = sanitize_for_react(tool_output)

    if payload is None or isinstance(payload, dict | list | str):
        return payload

    return truncate_text(payload)
