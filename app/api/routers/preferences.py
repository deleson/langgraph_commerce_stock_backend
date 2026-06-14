"""用户偏好 API Router。

该 Router 提供当前用户偏好的读取和更新接口。
偏好会影响日报、候选评分、通知默认值等个性化能力，必须基于当前登录用户。
"""

from fastapi import APIRouter
from app.api.deps import AsyncCurrentUser,AsyncDBSession
from app.schemas.common import ApiResponse
from app.schemas.preference import UserPreferenceResponse,UserPreferenceUpdateRequest
from app.services.user_preference_service import AsyncUserPreferenceService
from app.utils.responses import success_response

router = APIRouter(prefix="/preferences",tags=["preferences"])

@router.get(
    "/me",
    summary="Get My Preference",
    response_model=ApiResponse[UserPreferenceResponse],
)
async def get_my_preference(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
):
    preference = await AsyncUserPreferenceService(db).get_or_create_my_preference(
        current_user
    )
    return success_response(data=UserPreferenceResponse.model_validate(preference))


@router.patch(
    "/me",
    summary="Update My Preference",
    response_model=ApiResponse[UserPreferenceResponse],
)
async def update_my_preference(
    payload: UserPreferenceUpdateRequest,
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
):
    preference = await AsyncUserPreferenceService(db).update_my_preference(
        user=current_user,
        payload=payload,
    )
    return success_response(data=UserPreferenceResponse.model_validate(preference))
