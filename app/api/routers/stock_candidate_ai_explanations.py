from fastapi import APIRouter, status

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.common import ApiResponse
from app.schemas.stock_candidate_ai_explanation import (
    StockCandidateAIExplanationRequest,
    StockCandidateAIExplanationResponse,
)
from app.services.stock_candidate_ai_explanation_query_service import (
    StockCandidateAIExplanationQueryService,
)
from app.utils.responses import success_response


router = APIRouter(
    prefix="/stock-candidate-ai-explanations",
    tags=["stock-candidate-ai-explanations"],
)


@router.post(
    "",
    summary="Explain Stock Candidates With AI",
    description=(
        "Run deterministic stock candidate scoring first, then ask the LLM to "
        "generate Chinese explanations, comparisons, research priorities, and "
        "risk summaries. The AI explanation is based only on the scoring result, "
        "is for research only, and does not constitute investment advice."
    ),
    response_model=ApiResponse[StockCandidateAIExplanationResponse],
    status_code=status.HTTP_200_OK,
)
async def explain_stock_candidates_with_ai(
    payload: StockCandidateAIExplanationRequest,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[StockCandidateAIExplanationResponse]:
    """Explain stock candidates for the current user.

    The router only handles HTTP concerns:
    - receive and validate request payload
    - require authenticated user
    - inject AsyncSession
    - call StockCandidateAIExplanationQueryService
    - return unified API response
    """

    result = await StockCandidateAIExplanationQueryService(db).run_ai_explanation(
        request=payload,
        user=current_user,
    )
    return success_response(data=result)