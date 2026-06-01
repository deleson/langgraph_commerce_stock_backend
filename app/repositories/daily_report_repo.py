from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_report import DailyReport
from app.schemas.daily_report import (
    DailyReportCreate,
    DailyReportListQuery,
    DailyReportUpdate,
)


class AsyncDailyReportRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_report(
        self,
        payload: DailyReportCreate,
    ) -> DailyReport:
        report_data = payload.model_dump(mode="json")
        report_data["report_date"] = payload.report_date

        report = DailyReport(**report_data)
        self.db.add(report)
        await self.db.commit()
        await self.db.refresh(report)
        return report

    async def get_report(
        self,
        *,
        report_id: int,
        user_id: int,
    ) -> DailyReport | None:
        stmt = select(DailyReport).where(
            DailyReport.id == report_id,
            DailyReport.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_report_by_date(
        self,
        *,
        user_id: int,
        report_date,
    ) -> DailyReport | None:
        stmt = select(DailyReport).where(
            DailyReport.user_id == user_id,
            DailyReport.report_date == report_date,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_reports(
        self,
        *,
        user_id: int,
        query: DailyReportListQuery,
    ) -> list[DailyReport]:
        stmt = self._apply_filters(
            select(DailyReport),
            user_id=user_id,
            query=query,
        )

        stmt = (
            stmt.order_by(DailyReport.report_date.desc(), DailyReport.created_at.desc())
            .offset(query.offset)
            .limit(query.limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_reports(
        self,
        *,
        user_id: int,
        query: DailyReportListQuery,
    ) -> int:
        stmt = self._apply_filters(
            select(func.count(DailyReport.id)),
            user_id=user_id,
            query=query,
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def update_report(
        self,
        report: DailyReport,
        payload: DailyReportUpdate,
    ) -> DailyReport:
        update_data = payload.model_dump(
            mode="json",
            exclude_unset=True,
        )

        for field, value in update_data.items():
            setattr(report, field, value)

        self.db.add(report)
        await self.db.commit()
        await self.db.refresh(report)
        return report

    async def set_notification(
        self,
        *,
        report: DailyReport,
        notification_id: int,
    ) -> DailyReport:
        report.notification_id = notification_id

        self.db.add(report)
        await self.db.commit()
        await self.db.refresh(report)
        return report

    def _apply_filters(
        self,
        stmt,
        *,
        user_id: int,
        query: DailyReportListQuery,
    ):
        stmt = stmt.where(DailyReport.user_id == user_id)

        if query.start_date is not None:
            stmt = stmt.where(DailyReport.report_date >= query.start_date)

        if query.end_date is not None:
            stmt = stmt.where(DailyReport.report_date <= query.end_date)

        if query.status is not None:
            stmt = stmt.where(DailyReport.status == query.status)

        if query.source is not None:
            stmt = stmt.where(DailyReport.source == query.source)

        return stmt
