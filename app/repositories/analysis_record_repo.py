"""AI 分析记录 Repository。

本文件封装 analysis_records 表的数据访问。analysis_thread_id 是主分析、普通追问
和 ReAct 追问之间的连接键，但查询时仍必须带 user_id 防止跨用户访问。
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_record import AnalysisRecord
from sqlalchemy.ext.asyncio import AsyncSession


class AnalysisRecordRepository:
    """同步分析记录数据访问对象。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_user_id(self, user_id: int) -> list[AnalysisRecord]:
        stmt = (
            select(AnalysisRecord)
            .where(AnalysisRecord.user_id == user_id)
            .order_by(AnalysisRecord.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_by_id_for_user(
        self,
        *,
        record_id: int,
        user_id: int,
    ) -> AnalysisRecord | None:
        stmt = select(AnalysisRecord).where(
            AnalysisRecord.id == record_id,
            AnalysisRecord.user_id == user_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_latest_by_thread_id_for_user(
        self,
        *,
        thread_id: str,
        user_id: int,
    ) -> AnalysisRecord | None:
        """按分析线程查询当前用户最新分析记录。

        thread_id 不是权限凭证，必须和 user_id 一起使用。
        """

        stmt = (
            select(AnalysisRecord)
            .where(
                AnalysisRecord.user_id == user_id,
                AnalysisRecord.analysis_thread_id == thread_id,
            )
            .order_by(AnalysisRecord.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalar_one_or_none()
    def create(
        self,
        *,
        user_id: int,
        symbol: str,
        market: str,
        analysis_type: str = "stock_basic",
        status: str = "completed",
        analysis_thread_id: str | None = None,
        summary: str | None = None,
        result_snapshot: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> AnalysisRecord:
        record = AnalysisRecord(
            user_id=user_id,
            analysis_thread_id=analysis_thread_id,
            symbol=symbol,
            market=market,
            analysis_type=analysis_type,
            status=status,
            summary=summary,
            result_snapshot=result_snapshot,
            error_message=error_message,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def save(self, record: AnalysisRecord) -> AnalysisRecord:
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record


class AsyncAnalysisRecordRepository:
    """异步分析记录数据访问对象。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_user_id(self, user_id: int) -> list[AnalysisRecord]:
        stmt = (
            select(AnalysisRecord)
            .where(AnalysisRecord.user_id == user_id)
            .order_by(AnalysisRecord.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_for_user(
        self,
        *,
        record_id: int,
        user_id: int,
    ) -> AnalysisRecord | None:
        stmt = select(AnalysisRecord).where(
            AnalysisRecord.id == record_id,
            AnalysisRecord.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_by_thread_id_for_user(
        self,
        *,
        thread_id: str,
        user_id: int,
    ) -> AnalysisRecord | None:
        """按分析线程查询当前用户最新分析记录。"""

        stmt = (
            select(AnalysisRecord)
            .where(
                AnalysisRecord.user_id == user_id,
                AnalysisRecord.analysis_thread_id == thread_id,
            )
            .order_by(AnalysisRecord.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: int,
        symbol: str,
        market: str,
        analysis_type: str = "stock_basic",
        status: str = "completed",
        analysis_thread_id: str | None = None,
        summary: str | None = None,
        result_snapshot: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> AnalysisRecord:
        record = AnalysisRecord(
            user_id=user_id,
            analysis_thread_id=analysis_thread_id,
            symbol=symbol,
            market=market,
            analysis_type=analysis_type,
            status=status,
            summary=summary,
            result_snapshot=result_snapshot,
            error_message=error_message,
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def save(self, record: AnalysisRecord) -> AnalysisRecord:
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record
