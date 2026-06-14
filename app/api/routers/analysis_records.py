"""分析记录 API Router。

该 Router 提供当前用户历史个股分析记录的列表和详情查询。
Router 层只注入当前用户和数据库会话，记录归属校验由 Service / Repository 继续保证。
"""

from fastapi import APIRouter

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.analysis_record import AnalysisRecordResponse
from app.schemas.common import ApiResponse
from app.services.analysis_record_service import AsyncAnalysisRecordService
from app.utils.responses import success_response

router = APIRouter(prefix="/analysis-records", tags=["analysis-records"])


@router.get(
    "",
    summary="List My Analysis Records",
    response_model=ApiResponse[list[AnalysisRecordResponse]],
)
async def list_my_analysis_records(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
):
    # Analysis records are user-owned audit data, so every query is scoped by CurrentUser.
    records = await AsyncAnalysisRecordService(db).list_my_records(current_user)
    return success_response(
        data=[AnalysisRecordResponse.model_validate(record) for record in records]
    )


@router.get(
    "/{record_id}",
    summary="Get My Analysis Record",
    response_model=ApiResponse[AnalysisRecordResponse],
)
async def get_my_analysis_record(
    record_id: int,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
):
    # Do not query by record_id alone; user scope prevents horizontal privilege leaks.
    record = await AsyncAnalysisRecordService(db).get_my_record(
        user=current_user,
        record_id=record_id,
    )
    return success_response(data=AnalysisRecordResponse.model_validate(record))
