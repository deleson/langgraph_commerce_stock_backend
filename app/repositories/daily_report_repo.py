"""每日简报 Repository。

本文件封装 daily_reports 表的数据访问。日报属于用户私有研究结果，
查询列表、详情和同日记录时都必须带 user_id。
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_report import DailyReport
from app.schemas.daily_report import (
    DailyReportCreate,
    DailyReportListQuery,
    DailyReportUpdate,
)


class AsyncDailyReportRepository:
    """异步每日简报数据访问对象。

    Repository 只保存确定性日报结果和 AI 润色状态，不决定日报内容如何生成。
    """

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

    async def get_report_by_notification_id(
        self,
        *,
        notification_id: int | None,
        user_id: int,
    ) -> DailyReport | None:
        stmt = select(DailyReport).where(
            DailyReport.notification_id == notification_id,
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
        """查询当前用户某一天的日报。

        同一天重复生成时，Service 层会基于这条记录决定复用或重建。
        """

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
        notification_id: int | None,
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
        """为日报列表和计数复用同一套筛选条件。"""

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
