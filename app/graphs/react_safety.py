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


def clamp_int(
    value: Any,
    *,
    default: int,
    min_value: int,
    max_value: int,
) -> int:
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
    text = str(value)

    if len(text) <= max_length:
        return text

    return f"{text[:max_length]}...[truncated]"


def safe_error_message(
    exc: Exception,
) -> str:
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
    payload = sanitize_for_react(tool_input)

    if isinstance(payload, dict):
        return payload

    return {}


def sanitize_tool_output(
    tool_output: Any,
) -> dict[str, Any] | list[Any] | str | None:
    payload = sanitize_for_react(tool_output)

    if payload is None or isinstance(payload, dict | list | str):
        return payload

    return truncate_text(payload)