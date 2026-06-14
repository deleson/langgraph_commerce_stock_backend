"""个股 AI 分析 API Router。

该 Router 提供主分析、普通追问和 ReAct 工具追问接口。
Router 层负责当前用户和请求响应，AI 调用、额度检查、图执行、结果落库和安全边界
由 StockAnalysisService 与 StockAnalysisReactService 处理。
"""

from fastapi import APIRouter, status

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.common import ApiResponse
from app.schemas.stock_analysis import (
    StockAnalysisFollowUpRequest,
    StockAnalysisFollowUpResponse,
    StockAnalysisRequest,
    StockAnalysisResponse,
)
from app.schemas.stock_analysis_react import (
    StockAnalysisReactFollowUpRequest,
    StockAnalysisReactFollowUpResponse,
)
from app.services.stock_analysis_service import AsyncStockAnalysisService
from app.services.stock_analysis_react_service import StockAnalysisReactService
from app.utils.responses import success_response

router = APIRouter(prefix="/analysis", tags=["stock-analysis"])


@router.post(
    "/stock",
    summary="Analyze Stock",
    description=(
        "Run one stock analysis with LangGraph and DeepSeek. "
        "The response includes thread_id, graph_route, quality_context, "
        "market snapshot, basic indicators, and structured AI result."
    ),
    response_model=ApiResponse[StockAnalysisResponse],
    status_code=status.HTTP_201_CREATED,
)
async def analyze_stock(
    payload: StockAnalysisRequest,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[StockAnalysisResponse]:
    """为当前用户执行一次个股主分析。

    Router 只处理 HTTP 层职责：
    1. 接收请求体；
    2. 解析当前登录用户；
    3. 注入异步数据库会话；
    4. 调用 AsyncStockAnalysisService；
    5. 返回统一响应。
    """

    result = await AsyncStockAnalysisService(db).analyze_stock(
        user=current_user,
        payload=payload,
    )
    return success_response(data=result)


@router.post(
    "/stock/follow-up",
    summary="Follow Up Stock Analysis",
    description=(
        "Ask a follow-up question based on a previous stock analysis thread. "
        "The endpoint uses thread_id to find the current user's previous analysis context."
    ),
    response_model=ApiResponse[StockAnalysisFollowUpResponse],
)
async def follow_up_stock_analysis(
    payload: StockAnalysisFollowUpRequest,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[StockAnalysisFollowUpResponse]:
    """基于已有分析线程回答普通追问。

    普通追问会读取已有 AnalysisRecord 上下文，但不会重新执行完整主分析图，
    也不会调用 ReAct 工具链。它适合较轻量的上下文问答。
    """

    result = await AsyncStockAnalysisService(db).follow_up_stock_analysis(
        user=current_user,
        payload=payload,
    )
    return success_response(data=result)

@router.post(
    "/stock/react-follow-up",
    summary="ReAct Follow Up Stock Analysis",
    description=(
        "Ask a tool-augmented ReAct follow-up question based on a previous "
        "stock analysis thread. The endpoint requires analysis_thread_id, "
        "loads the current user's AnalysisRecord, runs a ReAct graph, and "
        "returns answer, used_tools, observations, and trace."
    ),
    response_model=ApiResponse[StockAnalysisReactFollowUpResponse],
)
async def react_follow_up_stock_analysis(
    payload: StockAnalysisReactFollowUpRequest,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[StockAnalysisReactFollowUpResponse]:
    """基于 ReAct 图回答工具增强追问。

    该接口要求传入已有 analysis_thread_id，并校验线程归属当前用户。
    ReAct 图只能在白名单工具范围内调用后端函数，并返回 observations 和 trace，
    方便后续调试、审计和解释。
    """

    result = await StockAnalysisReactService(db).follow_up_stock_analysis(
        user=current_user,
        payload=payload,
    )
    return success_response(data=result)
