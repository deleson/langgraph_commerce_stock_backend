from fastapi import APIRouter

from app.api.deps import AsyncDBSession, CurrentToken, CurrentUser, DBSession
from app.schemas.auth import (
    LogoutRequest,
    RefreshTokenRequest,
    TokenPairResponse,
    UserLoginRequest,
    UserRegisterRequest,
)
from app.schemas.common import ApiResponse
from app.schemas.user import UserResponse
from app.services.auth_service import AsyncAuthService, AuthService
from app.utils.responses import success_response

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    summary="Register User",
    response_model=ApiResponse[UserResponse],
)
async def register_user(
    payload: UserRegisterRequest,
    db: AsyncDBSession,
):
    user = await AsyncAuthService(db).register_user(payload)
    return success_response(data=UserResponse.model_validate(user))


@router.post(
    "/login",
    summary="Login User",
    response_model=ApiResponse[TokenPairResponse],
)
async def login_user(
    payload: UserLoginRequest,
    db: AsyncDBSession,
):
    auth_service = AsyncAuthService(db)
    user = await auth_service.authenticate_user(payload)
    access_token, refresh_token = await auth_service.issue_token_pair(user)

    return success_response(
        data=TokenPairResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
        )
    )


@router.post(
    "/refresh",
    summary="Refresh Token Pair",
    response_model=ApiResponse[TokenPairResponse],
)
async def refresh_token_pair(
    payload: RefreshTokenRequest,
    db: AsyncDBSession,
):
    access_token, refresh_token = await AsyncAuthService(db).refresh_user_tokens(
        payload.refresh_token
    )

    return success_response(
        data=TokenPairResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
        )
    )


@router.post(
    "/logout",
    summary="Logout Current Session",
    response_model=ApiResponse[dict[str, str]],
)
def logout_user(
    payload: LogoutRequest,
    db: DBSession,
    current_user: CurrentUser,
    current_token: CurrentToken,
):
    AuthService(db).logout_user(payload.refresh_token, current_token)
    return success_response(data={"message": "logout success"})