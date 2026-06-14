"""用户会话 Repository。

本文件封装 user_sessions 表的数据访问，用于 refresh token 会话创建、查询和撤销。
真实 token 明文不会落库，数据库中只保存 refresh_token_hash。
"""

from datetime import datetime

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
    ) -> UserSession:
        session = UserSession(
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            is_revoked=False,
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

    def revoke(self, session: UserSession) -> UserSession:
        session.is_revoked = True
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session


class AsyncUserSessionRepository:
    """异步用户会话数据访问对象。

    只负责会话记录读写；token 生成、黑名单和过期校验由 Service/Core 层处理。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        *,
        user_id: int,
        refresh_token_hash: str,
        expires_at: datetime,
    ) -> UserSession:
        session = UserSession(
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            is_revoked=False,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get_by_refresh_token_hash(
        self,
        refresh_token_hash: str,
    ) -> UserSession | None:
        stmt = select(UserSession).where(
            UserSession.refresh_token_hash == refresh_token_hash
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def save(self, session: UserSession) -> UserSession:
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def revoke(self, session: UserSession) -> UserSession:
        session.is_revoked = True
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session
