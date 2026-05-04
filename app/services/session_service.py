from datetime import UTC, datetime
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession


from app.core.exceptions import UnauthorizedException
from app.core.security import (
    get_refresh_token_expires_at,
    hash_refresh_token,
    verify_refresh_token,
)
from app.models.user_session import UserSession
from app.repositories.user_session_repo import UserSessionRepository,AsyncUserSessionRepository


class SessionService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.session_repo = UserSessionRepository(db)

    def create_refresh_session(self, *, user_id: int, refresh_token: str) -> UserSession:
        return self.session_repo.create(
            user_id=user_id,
            refresh_token_hash=hash_refresh_token(refresh_token),
            expires_at=get_refresh_token_expires_at(),
        )

    def validate_refresh_token(self, refresh_token: str) -> UserSession:
        refresh_token_hash = hash_refresh_token(refresh_token)
        session = self.session_repo.get_by_refresh_token_hash(refresh_token_hash)

        if session is None:
            raise UnauthorizedException(
                message="invalid refresh token",
                details=[{"field": "refresh_token", "reason": "refresh token is invalid"}],
            )

        if session.is_revoked:
            raise UnauthorizedException(
                message="refresh token has been revoked",
                details=[{"field": "refresh_token", "reason": "refresh token has been revoked"}],
            )

        if session.expires_at <= datetime.now(UTC):
            raise UnauthorizedException(
                message="refresh token has expired",
                details=[{"field": "refresh_token", "reason": "refresh token has expired"}],
            )

        if not verify_refresh_token(refresh_token, session.refresh_token_hash):
            raise UnauthorizedException(
                message="invalid refresh token",
                details=[{"field": "refresh_token", "reason": "refresh token is invalid"}],
            )

        return session

    def revoke_refresh_session(self,refresh_token:str) -> UserSession:
        session = self.validate_refresh_token(refresh_token)
        return self.session_repo.revoke(session)



class AsyncSessionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.session_repo = AsyncUserSessionRepository(db)

    async def create_refresh_session(
        self,
        *,
        user_id: int,
        refresh_token: str,
    ) -> UserSession:
        return await self.session_repo.create(
            user_id=user_id,
            refresh_token_hash=hash_refresh_token(refresh_token),
            expires_at=get_refresh_token_expires_at(),
        )

    async def validate_refresh_token(self, refresh_token: str) -> UserSession:
        refresh_token_hash = hash_refresh_token(refresh_token)
        session = await self.session_repo.get_by_refresh_token_hash(refresh_token_hash)

        if session is None:
            raise UnauthorizedException(
                message="invalid refresh token",
                details=[{"field": "refresh_token", "reason": "refresh token is invalid"}],
            )

        if session.is_revoked:
            raise UnauthorizedException(
                message="refresh token has been revoked",
                details=[
                    {
                        "field": "refresh_token",
                        "reason": "refresh token has been revoked",
                    }
                ],
            )

        if session.expires_at <= datetime.now(UTC):
            raise UnauthorizedException(
                message="refresh token has expired",
                details=[{"field": "refresh_token", "reason": "refresh token has expired"}],
            )

        if not verify_refresh_token(refresh_token, session.refresh_token_hash):
            raise UnauthorizedException(
                message="invalid refresh token",
                details=[{"field": "refresh_token", "reason": "refresh token is invalid"}],
            )

        return session

    async def revoke_refresh_session(self, refresh_token: str) -> UserSession:
        session = await self.validate_refresh_token(refresh_token)
        return await self.session_repo.revoke(session)