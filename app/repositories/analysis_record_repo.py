from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.analysis_record import AnalysisRecord


class AnalysisRecordRepository:
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

    def create(
        self,
        *,
        user_id: int,
        symbol: str,
        market: str,
        analysis_type: str = "stock_basic",
        status: str = "completed",
        summary: str | None = None,
        result_snapshot: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> AnalysisRecord:
        record = AnalysisRecord(
            user_id=user_id,
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