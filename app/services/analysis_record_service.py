"""分析记录 Service。

本文件负责当前用户 AI 分析记录的查询和创建。analysis_thread_id 用来连接主分析、
普通追问和 ReAct 追问，但不能代替 user_id 权限校验。
"""

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.analysis_record import AnalysisRecord
from app.models.user import User
from app.repositories.analysis_record_repo import AnalysisRecordRepository,AsyncAnalysisRecordRepository
from app.schemas.analysis_record import AnalysisRecordCreateRequest


class AnalysisRecordService:
    """同步分析记录业务服务。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.analysis_record_repo = AnalysisRecordRepository(db)

    def list_my_records(self, user: User) -> list[AnalysisRecord]:
        return self.analysis_record_repo.list_by_user_id(user.id)

    def get_my_record(self, *, user: User, record_id: int) -> AnalysisRecord:
        """查询当前用户的分析记录详情。"""

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
            analysis_thread_id=payload.analysis_thread_id,
            summary=payload.summary,
            result_snapshot=payload.result_snapshot,
            error_message=payload.error_message,
        )


class AsyncAnalysisRecordService:
    """异步分析记录业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.analysis_record_repo = AsyncAnalysisRecordRepository(db)

    async def list_my_records(self, user: User) -> list[AnalysisRecord]:
        return await self.analysis_record_repo.list_by_user_id(user.id)

    async def get_my_record(self, *, user: User, record_id: int) -> AnalysisRecord:
        """查询当前用户的分析记录详情。"""

        record = await self.analysis_record_repo.get_by_id_for_user(
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

    async def create_record(
        self,
        *,
        user: User,
        payload: AnalysisRecordCreateRequest,
    ) -> AnalysisRecord:
        return await self.analysis_record_repo.create(
            user_id=user.id,
            symbol=payload.symbol,
            market=payload.market,
            analysis_type=payload.analysis_type,
            status=payload.status,
            analysis_thread_id=payload.analysis_thread_id,
            summary=payload.summary,
            result_snapshot=payload.result_snapshot,
            error_message=payload.error_message,
        )
