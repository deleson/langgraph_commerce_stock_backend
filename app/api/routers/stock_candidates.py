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
    """Run stock candidate scoring for the current user.

    The router only handles HTTP concerns:
    - receive and validate request payload
    - require authenticated user
    - inject AsyncSession
    - call StockCandidateQueryService
    - return unified API response
    """

    result = await StockCandidateQueryService(db).run_stock_candidates(
        request=payload,
        user=current_user,
    )
    return success_response(data=result)