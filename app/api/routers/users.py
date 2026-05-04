from fastapi import APIRouter

from app.api.deps import AsyncCurrentUser,AsyncDBSession
from app.schemas.common import ApiResponse
from app.schemas.user import UserResponse,UserUpdateRequest
from app.services.user_service import AsyncUserService
from app.utils.responses import success_response

router = APIRouter(prefix="/users",tags=["users"])

@router.get(
    "/me",
    summary="Get Current User",
    response_model=ApiResponse[UserResponse],
)
async def get_current_user_profile(
        current_user:AsyncCurrentUser,
):
    return success_response(data=UserResponse.model_validate(current_user))

@router.patch(
    "/me",
    summary="update Current User Profile",
    response_model=ApiResponse[UserResponse]
)
async def update_current_user_profile(
        payload:UserUpdateRequest,
        current_user:AsyncCurrentUser,
        db:AsyncDBSession,
):
    user = await AsyncUserService(db).update_user_profile(current_user,payload)
    return success_response(data=UserResponse.model_validate(user))

