"""AI 用量与额度 API Router。

该 Router 提供当前用户 AI 额度、AI 调用日志和额度预检查接口。
它只负责 HTTP 层参数与当前用户上下文，额度计算和用量统计由
AIUsageQueryService 等业务服务完成。
"""

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
    """查询当前用户的 AI 额度汇总。

    Router 只负责当前用户和数据库会话。
    额度账户、今日用量、本月用量和剩余额度由 AIUsageQueryService 汇总。
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
    """查询当前用户的 AI 调用日志。

    user_id 来自登录 token，而不是查询参数，避免用户读取其他人的 AI 用量记录。
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
    """为当前用户执行 AI 额度预检查。

    请求体只提供预估 token / cost，Router 会强制使用当前登录用户 id，
    避免调用方通过请求体检查其他用户额度。
    """

    safe_payload = payload.model_copy(
        update={
            "user_id": current_user.id,
        }
    )

    result = await AIUsageQueryService(db).check_quota(safe_payload)
    return success_response(data=result)
