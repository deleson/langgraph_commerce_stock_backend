"""用户会话 Service。

本文件负责 refresh token 会话管理。refresh token 不是只靠客户端保存，
服务端也会保存其哈希和过期时间，用于撤销、过期校验和安全轮换。
"""

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
    """同步 refresh token 会话服务。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.session_repo = UserSessionRepository(db)

    def create_refresh_session(self, *, user_id: int, refresh_token: str) -> UserSession:
        """创建 refresh token 会话。

        数据库只保存 refresh token 的哈希，避免真实 token 泄露后可直接复用。
        """

        return self.session_repo.create(
            user_id=user_id,
            refresh_token_hash=hash_refresh_token(refresh_token),
            expires_at=get_refresh_token_expires_at(),
        )

    def validate_refresh_token(self, refresh_token: str) -> UserSession:
        """校验 refresh token 是否存在、未撤销、未过期且哈希匹配。"""

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
        """撤销 refresh token 会话。"""

        session = self.validate_refresh_token(refresh_token)
        return self.session_repo.revoke(session)



class AsyncSessionService:
    """异步 refresh token 会话服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.session_repo = AsyncUserSessionRepository(db)

    async def create_refresh_session(
        self,
        *,
        user_id: int,
        refresh_token: str,
    ) -> UserSession:
        """创建 refresh token 会话。"""

        return await self.session_repo.create(
            user_id=user_id,
            refresh_token_hash=hash_refresh_token(refresh_token),
            expires_at=get_refresh_token_expires_at(),
        )

    async def validate_refresh_token(self, refresh_token: str) -> UserSession:
        """校验 refresh token 是否仍然可用。"""

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
        """撤销 refresh token 会话。"""

        session = await self.validate_refresh_token(refresh_token)
        return await self.session_repo.revoke(session)
