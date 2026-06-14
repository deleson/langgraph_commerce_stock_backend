"""候选股票 AI 解释 API Router。

该 Router 提供候选评分结果的 AI 解释接口。
AI 只能解释已有确定性评分、等级和排名，不能修改候选结果本身。
"""

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
    """为当前用户生成候选股票 AI 解释。

    Router 只负责请求体、当前用户和数据库会话。
    确定性候选评分、AI 解释生成、额度检查和安全 fallback
    由 StockCandidateAIExplanationQueryService 处理。
    """

    result = await StockCandidateAIExplanationQueryService(db).run_ai_explanation(
        request=payload,
        user=current_user,
    )
    return success_response(data=result)
