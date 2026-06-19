"""API 依赖定义。

集中定义 Router 常用依赖，例如异步数据库会话、Bearer Token 和当前登录用户。
所有需要登录的接口都应通过 AsyncCurrentUser 获取用户，避免信任请求体中的 user_id。
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_async_db
from app.core.exceptions import UnauthorizedException
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.user_repo import AsyncUserRepository
from app.services.session_service import AsyncSessionService
from app.services.token_blacklist_service import TokenBlacklistService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

AsyncDBSession = Annotated[AsyncSession, Depends(get_async_db)]
CurrentToken = Annotated[str, Depends(oauth2_scheme)]


async def get_current_user_async(
    db: AsyncDBSession,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    """根据 JWT access token 解析当前用户。

    除了检查 token 黑名单和用户状态，本依赖还会按配置校验服务端 session。
    这样同类设备新登录撤销旧 session 后，旧 access token 也会立即失效。
    """

    payload = decode_access_token(token)

    if get_settings().auth_access_token_session_check_enabled:
        await AsyncSessionService(db).validate_access_session(
            session_id=payload.session_id,
            user_id=payload.user_id,
        )

    if TokenBlacklistService().is_access_token_blacklisted(payload.jti):
        raise UnauthorizedException(
            message="token has been revoked",
            details=[{"field": "authorization", "reason": "token is blacklisted"}],
        )

    user = await AsyncUserRepository(db).get_by_id(payload.user_id)

    if user is None:
        raise UnauthorizedException(
            message="user not found for token",
            details=[{"field": "authorization", "reason": "user does not exist"}],
        )

    if not user.is_active or user.status != "active":
        raise UnauthorizedException(
            message="user is inactive or suspended",
            details=[
                {
                    "field": "authorization",
                    "reason": "user is not allowed to access",
                }
            ],
        )

    return user


AsyncCurrentUser = Annotated[User, Depends(get_current_user_async)]