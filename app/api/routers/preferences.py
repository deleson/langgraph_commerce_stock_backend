from fastapi import APIRouter
from app.api.deps import CurrentUser,DBSession
from app.schemas.common import ApiResponse
from app.schemas.preference import UserPreferenceResponse,UserPreferenceUpdateRequest
from app.services.user_preference_service import UserPreferenceService
from app.utils.responses import success_response

router = APIRouter(prefix="/preferences",tags=["preferences"])

@router.get(
    "/me",
    summary="Get My Preference",
    response_model=ApiResponse[UserPreferenceResponse],
)
def get_my_preference(
        current_user:CurrentUser,
        db:DBSession,
):
    preference = UserPreferenceService(db).get_or_create_my_preference(current_user)
    return success_response(data=UserPreferenceResponse.model_validate(preference))

@router.patch(
    "/me",
    summary="Update My Preference",
    response_model=ApiResponse[UserPreferenceResponse],
)
def update_my_preference(
        payload:UserPreferenceUpdateRequest,
        current_user:CurrentUser,
        db:DBSession
):
    preference = UserPreferenceService(db).update_my_preference(
        user=current_user,
        payload=payload,
    )
    return success_response(data=UserPreferenceResponse.model_validate(preference))