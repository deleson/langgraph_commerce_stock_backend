"""用户会话 Service。

本文件负责 refresh token 会话管理，以及 access token 与服务端 session 的绑定校验。
refresh token 不是只靠客户端保存，服务端会保存 hash 以支持撤销、轮换和同类设备互踢。
"""

from datetime import UTC, datetime
import hashlib

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedException
from app.core.security import (
    get_refresh_token_expires_at,
    hash_refresh_token,
    verify_refresh_token,
)
from app.models.user_session import UserSession
from app.repositories.user_session_repo import UserSessionRepository, AsyncUserSessionRepository

MOBILE_PLATFORMS = {"android", "ios"}
VALID_PLATFORMS = {"android", "ios", "web", "unknown"}
VALID_CATEGORIES = {"mobile", "web", "unknown"}


class SessionService:
    """同步 refresh token 会话服务。"""

    def __init__(self, db: Session) -> None:
        self.session_repo = UserSessionRepository(db)

    def create_refresh_session(
        self,
        *,
        user_id: int,
        refresh_token: str,
        device_id: int | None = None,
        device_platform: str = "unknown",
        device_category: str = "unknown",
        device_fingerprint_hash: str | None = None,
        app_version: str | None = None,
        access_token_jti: str | None = None,
    ) -> UserSession:
        return self.session_repo.create(
            user_id=user_id,
            refresh_token_hash=hash_refresh_token(refresh_token),
            expires_at=get_refresh_token_expires_at(),
            device_id=device_id,
            device_platform=device_platform,
            device_category=device_category,
            device_fingerprint_hash=device_fingerprint_hash,
            app_version=app_version,
            access_token_jti=access_token_jti,
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
                details=[{"field": "refresh_token", "reason": session.revoked_reason or "refresh token has been revoked"}],
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

    def revoke_refresh_session(
        self,
        refresh_token: str,
        *,
        reason: str = "logout",
    ) -> UserSession:
        session = self.validate_refresh_token(refresh_token)
        return self.session_repo.revoke(session, reason=reason)


class AsyncSessionService:
    """异步 refresh token / access session 服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.session_repo = AsyncUserSessionRepository(db)

    @staticmethod
    def normalize_platform(platform: str | None) -> str:
        normalized = (platform or "unknown").strip().lower()
        return normalized if normalized in VALID_PLATFORMS else "unknown"

    @classmethod
    def resolve_device_category(cls, platform: str | None) -> str:
        normalized = cls.normalize_platform(platform)
        if normalized in MOBILE_PLATFORMS:
            return "mobile"
        if normalized == "web":
            return "web"
        return "unknown"

    @staticmethod
    def hash_device_fingerprint(device_fingerprint: str | None) -> str | None:
        if not device_fingerprint:
            return None
        return hashlib.sha256(device_fingerprint.encode("utf-8")).hexdigest()

    async def create_refresh_session(
        self,
        *,
        user_id: int,
        refresh_token: str,
        device_id: int | None = None,
        device_platform: str = "unknown",
        device_category: str = "unknown",
        device_fingerprint_hash: str | None = None,
        app_version: str | None = None,
        access_token_jti: str | None = None,
    ) -> UserSession:
        return await self.session_repo.create(
            user_id=user_id,
            refresh_token_hash=hash_refresh_token(refresh_token),
            expires_at=get_refresh_token_expires_at(),
            device_id=device_id,
            device_platform=self.normalize_platform(device_platform),
            device_category=device_category if device_category in VALID_CATEGORIES else "unknown",
            device_fingerprint_hash=device_fingerprint_hash,
            app_version=app_version,
            access_token_jti=access_token_jti,
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
                details=[{"field": "refresh_token", "reason": session.revoked_reason or "refresh token has been revoked"}],
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

    async def validate_access_session(
        self,
        *,
        session_id: int | None,
        user_id: int,
    ) -> UserSession:
        if session_id is None:
            raise UnauthorizedException(
                message="session is required",
                details=[{"field": "authorization", "reason": "session_id is missing"}],
            )

        session = await self.session_repo.get_by_id(session_id)
        if session is None or session.user_id != user_id:
            raise UnauthorizedException(
                message="session not found for token",
                details=[{"field": "authorization", "reason": "session does not exist"}],
            )

        if session.is_revoked:
            raise UnauthorizedException(
                message="session has been revoked",
                details=[{"field": "authorization", "reason": session.revoked_reason or "session has been revoked"}],
            )

        if session.expires_at <= datetime.now(UTC):
            raise UnauthorizedException(
                message="session has expired",
                details=[{"field": "authorization", "reason": "session has expired"}],
            )

        return session

    async def revoke_refresh_session(
        self,
        refresh_token: str,
        *,
        reason: str = "logout",
    ) -> UserSession:
        session = await self.validate_refresh_token(refresh_token)
        return await self.session_repo.revoke(session, reason=reason)

    async def revoke_same_category_sessions(
        self,
        *,
        user_id: int,
        device_category: str,
        replaced_by_session_id: int,
    ) -> list[UserSession]:
        """撤销同一用户同一设备类别的旧有效会话。

        这里不跨类别撤销，避免手机登录把 Web 管理端踢下线。unknown 是否参与互踢由
        AuthService 根据配置判断。
        """

        sessions = await self.session_repo.list_active_by_user_and_category(
            user_id=user_id,
            device_category=device_category,
            exclude_session_id=replaced_by_session_id,
        )
        revoked: list[UserSession] = []
        for session in sessions:
            revoked.append(
                await self.session_repo.revoke(
                    session,
                    reason="replaced_by_same_category_login",
                    replaced_by_session_id=replaced_by_session_id,
                )
            )
        return revoked