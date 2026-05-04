from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_db
from app.core.exceptions import UnauthorizedException
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.user_repo import AsyncUserRepository
from app.services.token_blacklist_service import TokenBlacklistService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

AsyncDBSession = Annotated[AsyncSession, Depends(get_async_db)]
CurrentToken = Annotated[str, Depends(oauth2_scheme)]


async def get_current_user_async(
    db: AsyncDBSession,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    payload = decode_access_token(token)

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
