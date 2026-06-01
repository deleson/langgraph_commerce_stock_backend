from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.user import User
from app.repositories.daily_report_repo import AsyncDailyReportRepository
from app.schemas.daily_report import (
    DailyReportGenerateRequest,
    DailyReportGenerationResponse,
    DailyReportListQuery,
    DailyReportListResponse,
    DailyReportResponse,
    DailyReportSource,
    DailyReportStatus,
    DailyReportTodayResponse,
    DailyReportUpdate,
)
from app.schemas.notification import NotificationCreateRequest
from app.services.daily_report_ai_service import DailyReportAIService
from app.services.daily_report_data_service import DailyReportDataService
from app.services.daily_report_service import DailyReportService
from app.services.notification_service import AsyncNotificationService

logger = logging.getLogger(__name__)


class DailyReportQueryService:
    """Daily report business orchestration service.

    This service is the unified entry for API and background tasks.
    It does not directly calculate market indicators and does not directly call
    repositories outside the daily report boundary.
    """

    DEFAULT_TIMEZONE = "Asia/Shanghai"

    def __init__(
        self,
        db: AsyncSession,
        *,
        repo: AsyncDailyReportRepository | None = None,
        data_service: DailyReportDataService | None = None,
        report_service: DailyReportService | None = None,
        ai_service: DailyReportAIService | None = None,
        notification_service: AsyncNotificationService | None = None,
    ) -> None:
        self.db = db
        self.repo = repo or AsyncDailyReportRepository(db)
        self.data_service = data_service or DailyReportDataService(db)
        self.report_service = report_service or DailyReportService()
        self.ai_service = ai_service or DailyReportAIService()
        self.notification_service = notification_service or AsyncNotificationService(db)

    async def generate_daily_report(
        self,
        *,
        user: User,
        request: DailyReportGenerateRequest,
        source: DailyReportSource = DailyReportSource.API,
    ) -> DailyReportGenerationResponse:
        report_date = request.report_date or self._today()

        existing_report = await self.repo.get_report_by_date(
            user_id=user.id,
            report_date=report_date,
        )

        if existing_report is not None and not request.force_rebuild:
            response = self._build_response(existing_report)
            return DailyReportGenerationResponse(
                report=response,
                created=False,
                notification_created=False,
                ai_used=response.ai_used,
                fallback_used=self._is_fallback_response(response),
            )

        data_context = await self.data_service.collect_daily_report_data(
            user=user,
            request=request,
            report_date=report_date,
            source=source,
        )

        report_payload = self.report_service.build_deterministic_report(data_context)

        if request.use_ai and report_payload.status != DailyReportStatus.FAILED:
            ai_result = await self.ai_service.enhance_report(
                report_payload,
                user_id=user.id,
            )
            report_payload = ai_result.report

        if existing_report is None:
            report_model = await self.repo.create_report(report_payload)
            created = True
        else:
            report_model = await self.repo.update_report(
                existing_report,
                self._build_update_payload(report_payload),
            )
            created = False

        notification_created = False
        if request.notify:
            report_model, notification_created = await self._create_notification_for_report(
                user=user,
                report=report_model,
            )

        response = self._build_response(report_model)

        return DailyReportGenerationResponse(
            report=response,
            created=created,
            notification_created=notification_created,
            ai_used=response.ai_used,
            fallback_used=self._is_fallback_response(response),
        )

    async def get_report(
        self,
        *,
        user_id: int,
        report_id: int,
    ) -> DailyReportResponse:
        report = await self.repo.get_report(
            user_id=user_id,
            report_id=report_id,
        )
        if report is None:
            raise NotFoundException("daily report not found")

        return self._build_response(report)

    async def get_today_report(
        self,
        *,
        user_id: int,
    ) -> DailyReportTodayResponse:
        report = await self.repo.get_report_by_date(
            user_id=user_id,
            report_date=self._today(),
        )

        if report is None:
            return DailyReportTodayResponse(
                exists=False,
                report=None,
                message="今日每日简报尚未生成。",
            )

        return DailyReportTodayResponse(
            exists=True,
            report=self._build_response(report),
            message=None,
        )

    async def list_reports(
        self,
        *,
        user_id: int,
        query: DailyReportListQuery,
    ) -> DailyReportListResponse:
        total = await self.repo.count_reports(
            user_id=user_id,
            query=query,
        )
        items = await self.repo.list_reports(
            user_id=user_id,
            query=query,
        )

        return DailyReportListResponse(
            total=total,
            items=[self._build_response(item) for item in items],
        )

    def _build_update_payload(
        self,
        report_payload,
    ) -> DailyReportUpdate:
        return DailyReportUpdate(
            status=report_payload.status,
            source=report_payload.source,
            summary=report_payload.summary,
            sections=report_payload.sections,
            stock_snapshots=report_payload.stock_snapshots,
            input_snapshot=report_payload.input_snapshot,
            market_snapshot=report_payload.market_snapshot,
            technical_snapshot=report_payload.technical_snapshot,
            strategy_signal_snapshot=report_payload.strategy_signal_snapshot,
            candidate_snapshot=report_payload.candidate_snapshot,
            profile_snapshot=report_payload.profile_snapshot,
            memory_snapshot=report_payload.memory_snapshot,
            ai_used=report_payload.ai_used,
            ai_status=report_payload.ai_status,
            ai_usage_log_id=report_payload.ai_usage_log_id,
            notification_id=report_payload.notification_id,
            unavailable_reason=report_payload.unavailable_reason,
            warnings=report_payload.warnings,
            disclaimer=report_payload.disclaimer,
        )

    def _build_response(
        self,
        report,
    ) -> DailyReportResponse:
        return DailyReportResponse.model_validate(report)

    def _is_fallback_response(
        self,
        response: DailyReportResponse,
    ) -> bool:
        return (
            response.status == "fallback"
            or response.ai_status in {"quota_blocked", "llm_error", "parse_error", "fallback"}
        )

    def _today(self):
        return datetime.now(ZoneInfo(self.DEFAULT_TIMEZONE)).date()

    async def _create_notification_for_report(
        self,
        *,
        user: User,
        report,
    ) -> tuple[object, bool]:
        if report.notification_id is not None:
            return report, False

        try:
            notification = await self.notification_service.create_notification(
                user=user,
                payload=NotificationCreateRequest(
                    title=self._build_notification_title(report),
                    content=self._build_notification_content(report),
                    notification_type="daily_report",
                    related_record_id=None,
                ),
            )

            updated_report = await self.repo.set_notification(
                report=report,
                notification_id=notification.id,
            )
            return updated_report, True
        except Exception:
            logger.exception("create daily report notification failed")
            return report, False

    def _build_notification_title(
        self,
        report,
    ) -> str:
        if report.status == "generated":
            return f"{report.report_date} 每日简报已生成"

        if report.status == "fallback":
            return f"{report.report_date} 每日简报已降级生成"

        return f"{report.report_date} 每日简报生成失败"

    def _build_notification_content(
        self,
        report,
    ) -> str:
        if report.status == "generated":
            prefix = "你的每日简报已生成，可以查看自选股行情、策略信号、候选评分和风险提示。"
        elif report.status == "fallback":
            prefix = "你的每日简报已生成，但 AI 润色不可用，系统已降级使用确定性简报。"
        else:
            prefix = "你的每日简报暂时未能完整生成，请检查自选股或行情数据是否可用。"

        warning_text = ""
        if report.warnings:
            warning_text = f" 提示：{str(report.warnings[0])[:120]}"

        return f"{prefix}{warning_text} 本简报仅作为研究参考，不构成投资建议。"
