from fastapi import APIRouter

from app.api.deps import CurrentUser, DBSession
from app.schemas.analysis_record import AnalysisRecordResponse
from app.schemas.common import ApiResponse
from app.services.analysis_record_service import AnalysisRecordService
from app.utils.responses import success_response

router = APIRouter(prefix="/analysis-records", tags=["analysis-records"])


@router.get(
    "",
    summary="List My Analysis Records",
    response_model=ApiResponse[list[AnalysisRecordResponse]],
)
def list_my_analysis_records(
    current_user: CurrentUser,
    db: DBSession,
):
    # Analysis records are user-owned audit data, so every query is scoped by CurrentUser.
    records = AnalysisRecordService(db).list_my_records(current_user)
    return success_response(
        data=[AnalysisRecordResponse.model_validate(record) for record in records]
    )


@router.get(
    "/{record_id}",
    summary="Get My Analysis Record",
    response_model=ApiResponse[AnalysisRecordResponse],
)
def get_my_analysis_record(
    record_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    # Do not query by record_id alone; user scope prevents horizontal privilege leaks.
    record = AnalysisRecordService(db).get_my_record(
        user=current_user,
        record_id=record_id,
    )
    return success_response(data=AnalysisRecordResponse.model_validate(record))