"""用户会话 Repository。

封装 user_sessions 表的数据访问，用于 refresh token 会话创建、查询、撤销和
同类设备单会话控制。真实 token 明文不会落库，数据库中只保存 hash / jti。
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.user_session import UserSession


class UserSessionRepository:
    """同步用户会话数据访问对象。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        user_id: int,
        refresh_token_hash: str,
        expires_at: datetime,
        device_id: int | None = None,
        device_platform: str = "unknown",
        device_category: str = "unknown",
        device_fingerprint_hash: str | None = None,
        app_version: str | None = None,
        access_token_jti: str | None = None,
    ) -> UserSession:
        session = UserSession(
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            is_revoked=False,
            device_id=device_id,
            device_platform=device_platform,
            device_category=device_category,
            device_fingerprint_hash=device_fingerprint_hash,
            app_version=app_version,
            access_token_jti=access_token_jti,
            last_seen_at=datetime.now(UTC),
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_by_refresh_token_hash(self, refresh_token_hash: str) -> UserSession | None:
        stmt = select(UserSession).where(
            UserSession.refresh_token_hash == refresh_token_hash
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def save(self, session: UserSession) -> UserSession:
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def revoke(
        self,
        session: UserSession,
        *,
        reason: str = "logout",
        replaced_by_session_id: int | None = None,
    ) -> UserSession:
        session.is_revoked = True
        session.revoked_at = datetime.now(UTC)
        session.revoked_reason = reason
        session.replaced_by_session_id = replaced_by_session_id
        return self.save(session)


class AsyncUserSessionRepository:
    """异步用户会话数据访问对象。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        user_id: int,
        refresh_token_hash: str,
        expires_at: datetime,
        device_id: int | None = None,
        device_platform: str = "unknown",
        device_category: str = "unknown",
        device_fingerprint_hash: str | None = None,
        app_version: str | None = None,
        access_token_jti: str | None = None,
    ) -> UserSession:
        session = UserSession(
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            is_revoked=False,
            device_id=device_id,
            device_platform=device_platform,
            device_category=device_category,
            device_fingerprint_hash=device_fingerprint_hash,
            app_version=app_version,
            access_token_jti=access_token_jti,
            last_seen_at=datetime.now(UTC),
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get_by_id(
        self,
        session_id: int,
    ) -> UserSession | None:
        return await self.db.get(UserSession, session_id)

    async def get_by_refresh_token_hash(
        self,
        refresh_token_hash: str,
    ) -> UserSession | None:
        stmt = select(UserSession).where(
            UserSession.refresh_token_hash == refresh_token_hash
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active_by_user_and_category(
        self,
        *,
        user_id: int,
        device_category: str,
        exclude_session_id: int | None = None,
    ) -> list[UserSession]:
        stmt = select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.device_category == device_category,
            UserSession.is_revoked.is_(False),
            UserSession.expires_at > datetime.now(UTC),
        )
        if exclude_session_id is not None:
            stmt = stmt.where(UserSession.id != exclude_session_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def save(self, session: UserSession) -> UserSession:
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def revoke(
        self,
        session: UserSession,
        *,
        reason: str = "logout",
        replaced_by_session_id: int | None = None,
    ) -> UserSession:
        session.is_revoked = True
        session.revoked_at = datetime.now(UTC)
        session.revoked_reason = reason
        session.replaced_by_session_id = replaced_by_session_id
        return await self.save(session)

    async def mark_seen(self, session: UserSession) -> UserSession:
        session.last_seen_at = datetime.now(UTC)
        return await self.save(session)