"""认证 API Router。

该 Router 提供注册、登录、刷新 token 和退出登录接口。
密码哈希、会话创建、refresh token 管理等安全细节由 AsyncAuthService 处理。
"""

from fastapi import APIRouter

from app.api.deps import AsyncDBSession, CurrentToken, AsyncCurrentUser
from app.schemas.auth import (
    LogoutRequest,
    RefreshTokenRequest,
    TokenPairResponse,
    UserLoginRequest,
    UserRegisterRequest,
)
from app.schemas.common import ApiResponse
from app.schemas.user import UserResponse
from app.services.auth_service import AsyncAuthService
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
    token_pair = await auth_service.login_user(payload)

    return success_response(
        data=TokenPairResponse(
            access_token=token_pair.access_token,
            refresh_token=token_pair.refresh_token,
            token_type="bearer",
            session_id=token_pair.session_id,
            device_category=token_pair.device_category,
            replaced_sessions_count=token_pair.replaced_sessions_count,
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
async def logout_user(
    payload: LogoutRequest,
    db: AsyncDBSession,
    current_user: AsyncCurrentUser,
    current_token: CurrentToken,
):
    await AsyncAuthService(db).logout_user(payload.refresh_token, current_token)
    return success_response(data={"message": "logout success"})
