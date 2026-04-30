from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.models.analysis_record import AnalysisRecord
from app.models.user import User
from app.repositories.analysis_record_repo import AnalysisRecordRepository
from app.schemas.analysis_record import AnalysisRecordCreateRequest


class AnalysisRecordService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.analysis_record_repo = AnalysisRecordRepository(db)

    def list_my_records(self, user: User) -> list[AnalysisRecord]:
        return self.analysis_record_repo.list_by_user_id(user.id)

    def get_my_record(self, *, user: User, record_id: int) -> AnalysisRecord:
        record = self.analysis_record_repo.get_by_id_for_user(
            record_id=record_id,
            user_id=user.id,
        )
        if record is None:
            raise NotFoundException(
                message="analysis record not found",
                details=[
                    {
                        "field": "record_id",
                        "reason": "analysis record does not exist",
                    }
                ],
            )

        return record

    def create_record(
        self,
        *,
        user: User,
        payload: AnalysisRecordCreateRequest,
    ) -> AnalysisRecord:
        return self.analysis_record_repo.create(
            user_id=user.id,
            symbol=payload.symbol,
            market=payload.market,
            analysis_type=payload.analysis_type,
            status=payload.status,
            summary=payload.summary,
            result_snapshot=payload.result_snapshot,
            error_message=payload.error_message,
        )