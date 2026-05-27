from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.stock_candidate import StockCandidateRequest
from app.schemas.stock_candidate_ai_explanation import (
    StockCandidateAIExplanationRequest,
    StockCandidateAIExplanationResponse,
)
from app.services.stock_candidate_ai_explanation_service import (
    StockCandidateAIExplanationService,
)
from app.services.stock_candidate_query_service import StockCandidateQueryService


class StockCandidateAIExplanationQueryService:
    """Orchestrate stock candidate scoring and AI explanation.

    This service keeps the future API router thin:
    - first run deterministic stock candidate scoring
    - then generate AI explanation based on that scoring result

    It does not score stocks directly and does not build prompts directly.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        candidate_query_service: StockCandidateQueryService | None = None,
        ai_explanation_service: StockCandidateAIExplanationService | None = None,
    ) -> None:
        self.db = db
        self.candidate_query_service = (
            candidate_query_service or StockCandidateQueryService(db)
        )
        self.ai_explanation_service = (
            ai_explanation_service or StockCandidateAIExplanationService()
        )

    async def run_ai_explanation(
        self,
        *,
        request: StockCandidateAIExplanationRequest,
        user: User,
    ) -> StockCandidateAIExplanationResponse:
        candidate_request = self._build_candidate_request_for_ai(request)

        candidate_result = await self.candidate_query_service.run_stock_candidates(
            request=candidate_request,
            user=user,
        )

        return await self.ai_explanation_service.explain_candidates(
            request=request,
            candidate_result=candidate_result,
            user_id=user.id,
        )

    def _build_candidate_request_for_ai(
        self,
        request: StockCandidateAIExplanationRequest,
    ) -> StockCandidateRequest:
        """Force the candidate result to include fields needed by AI explanation."""

        return request.candidate_request.model_copy(
            update={
                "include_score_breakdown": True,
                "include_strategy_signal": True,
                "include_data_quality": True,
            }
        )