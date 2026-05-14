from app.graphs.react_states import StockAnalysisReactState
from app.graphs.react_tools import is_react_tool_allowed


def route_react_action(
    state: StockAnalysisReactState,
) -> str:
    """Route the ReAct graph by next_action and selected tool.

    This function does not execute tools.
    It only returns a route name for LangGraph conditional edges.
    """

    next_action = state.get("next_action")

    if next_action == "final_answer":
        return "final_answer"

    if next_action == "error":
        return "error"

    if next_action != "tool_call":
        return "error"

    tool_call = state.get("tool_call")
    if tool_call is None:
        return "error"

    allowed_tools = state.get("allowed_tools", [])
    tool_name = tool_call.tool_name

    if not is_react_tool_allowed(tool_name, allowed_tools):
        return "error"

    return tool_name