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
    """Analyze one stock for the current user.

    The router only handles HTTP concerns:
    - receive request payload
    - resolve current user
    - inject AsyncSession
    - call service
    - return unified response
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
    """Answer a follow-up question for a previous stock analysis.

    This is a minimal follow-up API:
    - it reads previous analysis context from AnalysisRecord
    - it does not run the full stock analysis graph again
    - it does not implement full ReAct tool calling yet
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
    """Answer a follow-up question with ReAct tool calling.

    This endpoint is stricter and more capable than the minimal follow-up API:
    - it requires an existing analysis_thread_id
    - it verifies the thread belongs to the current user
    - it lets the ReAct graph decide whether to call safe business tools
    - it returns tool observations and trace for debugging and audit
    """

    result = await StockAnalysisReactService(db).follow_up_stock_analysis(
        user=current_user,
        payload=payload,
    )
    return success_response(data=result)