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
    """Generate one daily report for the current user.

    The router only handles HTTP concerns:
    - receive and validate request payload
    - require authenticated user
    - inject AsyncSession
    - call DailyReportQueryService
    - return unified API response
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
    """List current user's daily reports."""

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
    """Get today's report for the current user."""

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
    """Get one daily report detail."""

    result = await DailyReportQueryService(db).get_report(
        user_id=current_user.id,
        report_id=report_id,
    )
    return success_response(data=result)