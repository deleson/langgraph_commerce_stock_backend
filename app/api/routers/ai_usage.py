from datetime import date
from fastapi import APIRouter, Query, status

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.ai_usage import (
    AIQuotaCheckRequest,
    AIQuotaCheckResult,
    AIQuotaSummaryResponse,
    AIUsageFeature,
    AIUsageLogListResponse,
    AIUsageQuery,
    AIUsageStatus,
)
from app.schemas.common import ApiResponse
from app.services.ai_usage_query_service import AIUsageQueryService
from app.utils.responses import success_response


router = APIRouter(prefix="/ai-usage", tags=["ai-usage"])


@router.get(
    "/quota",
    summary="Get AI Quota Summary",
    description=(
        "Get the current user's AI quota account, today's AI usage, "
        "current month AI usage, and remaining quota."
    ),
    response_model=ApiResponse[AIQuotaSummaryResponse],
    status_code=status.HTTP_200_OK,
)
async def get_ai_quota_summary(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[AIQuotaSummaryResponse]:
    """Get AI quota summary for the current user.

    The router only handles HTTP concerns:
    - require authenticated user
    - inject AsyncSession
    - call AIUsageQueryService
    - return unified API response
    """

    result = await AIUsageQueryService(db).get_quota_summary(
        user_id=current_user.id,
    )
    return success_response(data=result)


@router.get(
    "/logs",
    summary="List AI Usage Logs",
    description=(
        "List the current user's AI usage logs. "
        "This endpoint only returns logs that belong to the authenticated user."
    ),
    response_model=ApiResponse[AIUsageLogListResponse],
    status_code=status.HTTP_200_OK,
)
async def list_ai_usage_logs(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    feature: AIUsageFeature | None = Query(default=None),
    usage_status: AIUsageStatus | None = Query(default=None, alias="status"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> ApiResponse[AIUsageLogListResponse]:
    """List AI usage logs for the current user.

    The user_id is taken from the login token, not from query parameters,
    so users cannot read other users' usage logs.
    """

    query = AIUsageQuery(
        feature=feature,
        status=usage_status,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )

    result = await AIUsageQueryService(db).list_usage_logs(
        user_id=current_user.id,
        query=query,
    )
    return success_response(data=result)


@router.post(
    "/quota/check",
    summary="Check AI Quota",
    description=(
        "Check whether the current user has enough AI quota for an estimated "
        "AI call. This endpoint only checks quota and does not call the LLM."
    ),
    response_model=ApiResponse[AIQuotaCheckResult],
    status_code=status.HTTP_200_OK,
)
async def check_ai_quota(
    payload: AIQuotaCheckRequest,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[AIQuotaCheckResult]:
    """Check AI quota for the current user.

    The request body contains estimated token/cost numbers, but user_id is
    forced to the current authenticated user to prevent cross-user checks.
    """

    safe_payload = payload.model_copy(
        update={
            "user_id": current_user.id,
        }
    )

    result = await AIUsageQueryService(db).check_quota(safe_payload)
    return success_response(data=result)