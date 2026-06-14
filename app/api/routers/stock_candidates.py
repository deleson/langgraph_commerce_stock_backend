"""候选股票评分 API Router。

该 Router 提供基于手动股票池或用户上下文的候选评分入口。
候选评分用于研究优先级排序，不是荐股，也不承诺未来收益。
"""

from fastapi import APIRouter, status

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.common import ApiResponse
from app.schemas.stock_candidate import (
    StockCandidateRequest,
    StockCandidateResponse,
)
from app.services.stock_candidate_query_service import StockCandidateQueryService
from app.utils.responses import success_response


router = APIRouter(prefix="/stock-candidates", tags=["stock-candidates"])


@router.post(
    "",
    summary="Run Stock Candidate Scoring",
    description=(
        "Score and rank stock candidates from manual symbols or the current "
        "user's watchlist using market data quality, technical indicators, "
        "strategy signals, and user risk preference. This result is for "
        "research only and does not constitute investment advice."
    ),
    response_model=ApiResponse[StockCandidateResponse],
    status_code=status.HTTP_200_OK,
)
async def run_stock_candidates(
    payload: StockCandidateRequest,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[StockCandidateResponse]:
    """执行一次候选股票评分。

    候选评分会综合数据质量、技术指标、策略信号、回测表现和用户偏好。
    评分结果只是研究优先级，不是荐股，也不承诺未来收益。
    """

    result = await StockCandidateQueryService(db).run_stock_candidates(
        request=payload,
        user=current_user,
    )
    return success_response(data=result)
