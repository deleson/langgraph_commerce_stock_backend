"""ReAct 图条件路由。

这里只根据 agent_reason_node 写入的 next_action 和 tool_call 返回下一条边。
工具是否允许调用会在这里做一次白名单检查；真正执行仍在 tool_execution 节点中完成。
"""

from app.graphs.react_states import StockAnalysisReactState
from app.graphs.react_tools import is_react_tool_allowed


def route_react_action(
    state: StockAnalysisReactState,
) -> str:
    """根据 next_action 和工具白名单选择 ReAct 下一节点。

    该函数不执行工具，只返回 LangGraph conditional edge 的路由名称。
    如果模型选择了未授权工具，统一进入 error / final_answer 安全路径。
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
