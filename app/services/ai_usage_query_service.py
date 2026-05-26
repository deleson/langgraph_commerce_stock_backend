from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.ai_usage_repo import AsyncAIUsageRepository
from app.schemas.ai_usage import (
    AIQuotaCheckRequest,
    AIQuotaCheckResult,
    AIQuotaSummaryResponse,
    AIUsageLogListResponse,
    AIUsageQuery,
)
from app.services.ai_quota_service import AIQuotaService


class AIUsageQueryService:
    """Query AI usage data for API endpoints.

    This service is a read/query orchestration layer.
    It keeps routers thin and does not call the LLM or write usage logs.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        repo: AsyncAIUsageRepository | None = None,
        quota_service: AIQuotaService | None = None,
    ) -> None:
        self.db = db
        self.repo = repo or AsyncAIUsageRepository(db)
        self.quota_service = quota_service or AIQuotaService(self.repo)

    async def get_quota_summary(
        self,
        *,
        user_id: int,
        currency: str = "CNY",
    ) -> AIQuotaSummaryResponse:
        return await self.quota_service.get_quota_summary(
            user_id=user_id,
            currency=currency,
        )

    async def check_quota(
        self,
        request: AIQuotaCheckRequest,
    ) -> AIQuotaCheckResult:
        return await self.quota_service.check_quota(request)

    async def list_usage_logs(
        self,
        *,
        user_id: int,
        query: AIUsageQuery,
    ) -> AIUsageLogListResponse:
        items = await self.repo.list_usage_logs(
            user_id=user_id,
            query=query,
        )
        total = await self.repo.count_usage_logs(
            user_id=user_id,
            query=query,
        )

        return AIUsageLogListResponse(
            items=items,
            total=total,
            limit=query.limit,
        )