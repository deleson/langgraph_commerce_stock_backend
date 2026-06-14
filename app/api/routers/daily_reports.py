"""每日简报 API Router。

该 Router 提供每日简报生成、今日简报、列表和详情查询接口。
AI 仅可用于润色确定性简报内容，不能修改价格、评分、信号和风险边界。
"""

from datetime import date

from fastapi import APIRouter, Query, status

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.common import ApiResponse
from app.schemas.daily_report import (
    DailyReportGenerateRequest,
    DailyReportGenerationResponse,
    DailyReportListQuery,
    DailyReportListResponse,
    DailyReportResponse,
    DailyReportSource,
    DailyReportStatus,
    DailyReportTodayResponse,
)
from app.services.daily_report_query_service import DailyReportQueryService
from app.utils.responses import success_response


router = APIRouter(prefix="/daily-reports", tags=["daily-reports"])


@router.post(
    "/generate",
    summary="Generate Daily Report",
    description=(
        "Generate or reuse a daily report for the current user. "
        "The report is based on watchlist stocks, market data, strategy signals, "
        "candidate scoring, user profile, and relevant memories. "
        "AI polishing is optional and subject to AI usage quota."
    ),
    response_model=ApiResponse[DailyReportGenerationResponse],
    status_code=status.HTTP_200_OK,
)
async def generate_daily_report(
    payload: DailyReportGenerateRequest,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[DailyReportGenerationResponse]:
    """为当前用户生成或复用一份每日简报。

    Router 只负责请求体、当前用户和数据库会话。
    简报数据组装、AI 润色、通知生成和幂等复用由 DailyReportQueryService 编排。
    """

    result = await DailyReportQueryService(db).generate_daily_report(
        user=current_user,
        request=payload,
        source=DailyReportSource.API,
    )
    return success_response(data=result)


@router.get(
    "",
    summary="List Daily Reports",
    description=(
        "List daily reports owned by the current user. "
        "Users can only read their own report records."
    ),
    response_model=ApiResponse[DailyReportListResponse],
    status_code=status.HTTP_200_OK,
)
async def list_daily_reports(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    report_status: DailyReportStatus | None = Query(default=None, alias="status"),
    source: DailyReportSource | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[DailyReportListResponse]:
    """查询当前用户的每日简报列表。"""

    query = DailyReportListQuery(
        start_date=start_date,
        end_date=end_date,
        status=report_status,
        source=source,
        limit=limit,
        offset=offset,
    )

    result = await DailyReportQueryService(db).list_reports(
        user_id=current_user.id,
        query=query,
    )
    return success_response(data=result)


@router.get(
    "/today",
    summary="Get Today's Daily Report",
    description="Get today's daily report for the current user if it exists.",
    response_model=ApiResponse[DailyReportTodayResponse],
    status_code=status.HTTP_200_OK,
)
async def get_today_daily_report(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[DailyReportTodayResponse]:
    """查询当前用户今天的每日简报。"""

    result = await DailyReportQueryService(db).get_today_report(
        user_id=current_user.id,
    )
    return success_response(data=result)


@router.get(
    "/{report_id}",
    summary="Get Daily Report",
    description=(
        "Get one daily report by id. "
        "Users can only access their own reports."
    ),
    response_model=ApiResponse[DailyReportResponse],
    status_code=status.HTTP_200_OK,
)
async def get_daily_report(
    report_id: int,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
) -> ApiResponse[DailyReportResponse]:
    """查询当前用户拥有的一条每日简报详情。"""

    result = await DailyReportQueryService(db).get_report(
        user_id=current_user.id,
        report_id=report_id,
    )
    return success_response(data=result)
