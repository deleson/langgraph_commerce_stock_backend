from dataclasses import dataclass

from app.schemas.stock_analysis_react import ReactToolName


@dataclass(frozen=True)
class ReactToolDefinition:
    """Static definition for a ReAct tool.

    This class only describes what a tool is.
    It does not execute the tool.
    """

    name: ReactToolName
    description: str
    required_inputs: tuple[str, ...] = ()
    optional_inputs: tuple[str, ...] = ()


REACT_TOOL_DEFINITIONS: dict[ReactToolName, ReactToolDefinition] = {
    "get_analysis_record": ReactToolDefinition(
        name="get_analysis_record",
        description=(
            "Read the previous stock analysis record by analysis_thread_id. "
            "Use this before answering questions about the original analysis."
        ),
        required_inputs=("analysis_thread_id",),
    ),
    "get_market_overview": ReactToolDefinition(
        name="get_market_overview",
        description=(
            "Get market overview including quote, candles, basic indicators, "
            "technical indicators, data quality, and sync status."
        ),
        required_inputs=("symbol", "market"),
        optional_inputs=("timeframe", "limit", "include_technical_indicators"),
    ),
    "get_technical_indicators": ReactToolDefinition(
        name="get_technical_indicators",
        description=(
            "Get technical indicators such as MA, EMA, RSI, MACD, volatility, "
            "momentum, and volume factors."
        ),
        required_inputs=("symbol", "market"),
        optional_inputs=("timeframe", "limit", "adjust_type", "source"),
    ),
    "get_data_quality": ReactToolDefinition(
        name="get_data_quality",
        description=(
            "Get market data quality report for a stock, including missing data, "
            "stale data, duplicate candles, warnings, and errors."
        ),
        required_inputs=("symbol", "market"),
        optional_inputs=("timeframe", "source", "adjust_type"),
    ),
    "get_user_preference": ReactToolDefinition(
        name="get_user_preference",
        description=(
            "Get current user's risk preference, timezone, and notification settings. "
            "Use this when answering whether a stock fits the user's style."
        ),
    ),
    "get_watchlist": ReactToolDefinition(
        name="get_watchlist",
        description=(
            "Get current user's watchlist. Use this when the user asks about "
            "their selected stocks or wants comparison inside their watchlist."
        ),
    ),
    "get_backtest_result": ReactToolDefinition(
        name="get_backtest_result",
        description=(
            "Run a single-stock historical backtest for a specified symbol, market, "
            "and date range, then return a trimmed performance summary. Use this "
            "only to explain historical strategy performance, risk, drawdown, "
            "win rate, and benchmark comparison. It does not place real trades, "
            "predict future returns, or provide investment advice."
        ),
        required_inputs=("symbol", "market", "start_date", "end_date"),
        optional_inputs=(
            "initial_cash",
            "position_size_ratio",
            "timeframe",
            "adjust_type",
            "source",
            "min_required_candles",
            "enforce_data_quality",
            "data_quality_stale_after_days",
        ),
    ),
    "get_stock_candidates": ReactToolDefinition(
        name="get_stock_candidates",
        description=(
            "Get deterministic stock candidate scoring results from a manual symbol "
            "list or the current user's watchlist, then return a trimmed candidate "
            "summary with rank, score, grade, reasons, risks, score breakdown, "
            "strategy signal, and data quality. Use this when the user asks which "
            "stocks in a given pool or watchlist are more worth researching, asks "
            "to compare candidate scores, or asks why candidates are ranked. It "
            "does not freely recommend stocks, scan the whole market, place trades, "
            "predict future returns, or provide investment advice."
        ),
        optional_inputs=(
            "universe_source",
            "symbols",
            "top_n",
            "market",
            "timeframe",
            "limit",
            "min_required_candles",
            "adjust_type",
            "source",
            "include_excluded",
            "include_score_breakdown",
            "include_ai_explanation",
            "explanation_style",
            "max_candidates_to_explain",
            "enforce_data_quality",
            "data_quality_stale_after_days",
        ),
    ),
}

DEFAULT_REACT_TOOLS: tuple[ReactToolName, ...] = (
    "get_analysis_record",
    "get_market_overview",
    "get_technical_indicators",
    "get_data_quality",
    "get_user_preference",
    "get_watchlist",
    "get_backtest_result",
    "get_stock_candidates",
)

def get_default_react_tools() -> list[ReactToolName]:
    return list(DEFAULT_REACT_TOOLS)


def is_react_tool_allowed(
    tool_name: str,
    allowed_tools: list[ReactToolName],
) -> bool:
    return tool_name in allowed_tools and tool_name in REACT_TOOL_DEFINITIONS


def get_react_tool_definition(
    tool_name: ReactToolName,
) -> ReactToolDefinition:
    return REACT_TOOL_DEFINITIONS[tool_name]


def format_react_tool_descriptions(
    allowed_tools: list[ReactToolName],
) -> str:
    descriptions: list[str] = []

    for tool_name in allowed_tools:
        tool = get_react_tool_definition(tool_name)
        required = ", ".join(tool.required_inputs) or "none"
        optional = ", ".join(tool.optional_inputs) or "none"

        descriptions.append(
            "\n".join(
                [
                    f"- {tool.name}",
                    f"  description: {tool.description}",
                    f"  required_inputs: {required}",
                    f"  optional_inputs: {optional}",
                ]
            )
        )

    return "\n".join(descriptions)