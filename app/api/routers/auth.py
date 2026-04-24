from datetime import timedelta

from fastapi import APIRouter

from app.api.deps import DBSession
from app.core.config import get_settings
from app.core.security import create_access_token
from app.schemas.auth import TokenResponse, UserLoginRequest, UserRegisterRequest
from app.schemas.common import ApiResponse
from app.schemas.user import UserResponse
from app.services.auth_service import AuthService
from app.utils.responses import success_response

settings = get_settings()

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    summary="Register User",
    response_model=ApiResponse[UserResponse],
)
def register_user(
    payload: UserRegisterRequest,
    db: DBSession,
):
    user = AuthService(db).register_user(payload)
    return success_response(data=UserResponse.model_validate(user))


@router.post(
    "/login",
    summary="Login User",
    response_model=ApiResponse[TokenResponse],
)
def login_user(
    payload: UserLoginRequest,
    db: DBSession,
):
    user = AuthService(db).authenticate_user(payload)

    access_token = create_access_token(
        subject=user.email,
        user_id=user.id,
        is_superuser=user.is_superuser,
        expires_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes),
    )

    return success_response(
        data=TokenResponse(
            access_token=access_token,
            token_type="bearer",
        )
    )