from fastapi import APIRouter

from app.api.deps import CurrentUser,DBSession
from app.schemas.common import ApiResponse
from app.schemas.user import UserResponse,UserUpdateRequest
from app.services.user_service import UserService
from app.utils.responses import success_response

router = APIRouter(prefix="/users",tags=["users"])

@router.get(
    "/me",
    summary="Get Current User",
    response_model=ApiResponse[UserResponse],
)
def get_current_user_profile(
        current_user:CurrentUser,
):
    return success_response(data=UserResponse.model_validate(current_user))

@router.patch(
    "/me",
    summary="update Current User Profile",
    response_model=ApiResponse[UserResponse]
)
def update_current_user_profile(
        payload:UserUpdateRequest,
        current_user:CurrentUser,
        db:DBSession,
):
    user = UserService(db).update_user_profile(current_user,payload)
    return success_response(data=UserResponse.model_validate(user))

