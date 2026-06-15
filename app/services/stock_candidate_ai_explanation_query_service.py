"""候选股票 AI 解释查询编排服务。

这一层连接“确定性候选评分”和“AI 中文解释”：
API 调用进来后，先由 StockCandidateQueryService 计算候选结果，
再由 StockCandidateAIExplanationService 基于这个结果做解释。
这样可以保证 AI 解释永远站在后端确定性评分之上，而不是让 AI 自己选股。
"""

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
    """编排候选评分和候选 AI 解释。

    Router 只负责接收 HTTP 请求和当前用户；
    本 Service 负责先跑确定性候选评分，再把评分结果交给 AI 解释服务。
    它本身不直接打分，也不直接拼 Prompt。
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
        """执行候选 AI 解释主流程。

        先强制候选评分返回 score_breakdown、strategy_signal、data_quality，
        因为 AI 解释必须基于这些可审计字段，而不能只拿一个总分自由发挥。
        """

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
        """强制打开 AI 解释所需的候选评分详情字段。

        include_score_breakdown 用于解释分数来源；
        include_strategy_signal 用于解释规则信号；
        include_data_quality 用于解释数据可信度和风险。
        """

        return request.candidate_request.model_copy(
            update={
                "include_score_breakdown": True,
                "include_strategy_signal": True,
                "include_data_quality": True,
            }
        )
