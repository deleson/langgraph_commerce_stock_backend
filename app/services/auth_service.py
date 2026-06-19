"""认证业务 Service。

负责注册、登录、签发 token、刷新 token 和退出登录。Repository 只负责读写用户和
会话；密码哈希、JWT、refresh token 轮换、同类设备单会话和黑名单属于这里的
安全业务边界。
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ConflictException, UnauthorizedException
from app.core.security import (
    create_access_token,
    generate_access_token_jti,
    generate_refresh_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_preference_repo import UserPreferenceRepository, AsyncUserPreferenceRepository
from app.repositories.user_repo import UserRepository, AsyncUserRepository
from app.schemas.auth import UserLoginRequest, UserRegisterRequest
from app.schemas.device import DeviceRegisterRequest
from app.services.device_service import AsyncDeviceService
from app.services.session_service import SessionService, AsyncSessionService
from app.services.token_blacklist_service import TokenBlacklistService


@dataclass(slots=True)
class IssuedTokenPair:
    """登录链路签发 token 后的结构化结果。"""

    access_token: str
    refresh_token: str
    session_id: int
    device_category: str
    replaced_sessions_count: int = 0


class AuthService:
    """同步认证业务服务。

    早期同步接口保留该类；当前主要 API 链路更多使用 AsyncAuthService。
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.user_repo = UserRepository(db)

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _normalize_username(username: str) -> str:
        return username.strip()

    def register_user(self, payload: UserRegisterRequest) -> User:
        email = self._normalize_email(payload.email)
        username = self._normalize_username(payload.username)

        if self.user_repo.get_by_email(email):
            raise ConflictException(
                message="email already exists",
                details=[{"field": "email", "reason": "email already exists"}],
            )

        if self.user_repo.get_by_username(username):
            raise ConflictException(
                message="username already exists",
                details=[{"field": "username", "reason": "username already exists"}],
            )

        user = self.user_repo.create(
            email=email,
            username=username,
            hashed_password=hash_password(payload.password),
            is_active=True,
            is_superuser=False,
            status="active",
        )
        UserPreferenceRepository(self.db).create_default(user.id)
        return user

    def authenticate_user(self, payload: UserLoginRequest) -> User:
        email = self._normalize_email(payload.email)
        user = self.user_repo.get_by_email(email)

        if user is None or not verify_password(payload.password, user.hashed_password):
            raise UnauthorizedException(
                message="invalid email or password",
                details=[{"field": "email", "reason": "credentials are invalid"}],
            )

        if not user.is_active or user.status != "active":
            raise UnauthorizedException(
                message="user is not allowed to sign in",
                details=[{"field": "status", "reason": "user is inactive or suspended"}],
            )
        return user

    def issue_token_pair(self, user: User) -> tuple[str, str]:
        refresh_token = generate_refresh_token()
        session = SessionService(self.db).create_refresh_session(
            user_id=user.id,
            refresh_token=refresh_token,
        )
        access_jti = generate_access_token_jti()
        access_token = create_access_token(
            subject=user.email,
            user_id=user.id,
            is_superuser=user.is_superuser,
            session_id=session.id,
            jti=access_jti,
        )
        session.access_token_jti = access_jti
        SessionService(self.db).session_repo.save(session)
        return access_token, refresh_token

    def refresh_user_tokens(self, refresh_token: str) -> tuple[str, str]:
        session = SessionService(self.db).validate_refresh_token(refresh_token)
        user = self.user_repo.get_by_id(session.user_id)
        if user is None or not user.is_active or user.status != "active":
            raise UnauthorizedException(
                message="user is not allowed to refresh token",
                details=[{"field": "refresh_token", "reason": "user is invalid or inactive"}],
            )
        SessionService(self.db).revoke_refresh_session(refresh_token, reason="refresh_rotated")
        return self.issue_token_pair(user)

    def logout_user(self, refresh_token: str, access_token: str) -> None:
        SessionService(self.db).revoke_refresh_session(refresh_token, reason="logout")
        TokenBlacklistService().blacklist_access_token(access_token)


class AsyncAuthService:
    """异步认证业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = AsyncUserRepository(db)

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _normalize_username(username: str) -> str:
        return username.strip()

    async def register_user(self, payload: UserRegisterRequest) -> User:
        email = self._normalize_email(payload.email)
        username = self._normalize_username(payload.username)

        if await self.user_repo.get_by_email(email):
            raise ConflictException(
                message="email already exists",
                details=[{"field": "email", "reason": "email already exists"}],
            )

        if await self.user_repo.get_by_username(username):
            raise ConflictException(
                message="username already exists",
                details=[{"field": "username", "reason": "username already exists"}],
            )

        user = await self.user_repo.create(
            email=email,
            username=username,
            hashed_password=hash_password(payload.password),
            is_active=True,
            is_superuser=False,
            status="active",
        )
        await AsyncUserPreferenceRepository(self.db).create_default(user.id)
        return user

    async def authenticate_user(self, payload: UserLoginRequest) -> User:
        email = self._normalize_email(payload.email)
        user = await self.user_repo.get_by_email(email)

        if user is None or not verify_password(payload.password, user.hashed_password):
            raise UnauthorizedException(
                message="invalid email or password",
                details=[{"field": "email", "reason": "credentials are invalid"}],
            )

        if not user.is_active or user.status != "active":
            raise UnauthorizedException(
                message="user is not allowed to sign in",
                details=[{"field": "status", "reason": "user is inactive or suspended"}],
            )
        return user

    async def login_user(self, payload: UserLoginRequest) -> IssuedTokenPair:
        user = await self.authenticate_user(payload)
        session_service = AsyncSessionService(self.db)
        platform = session_service.normalize_platform(payload.platform)
        category = session_service.resolve_device_category(platform)
        device = await self._register_login_device_if_needed(user=user, payload=payload)

        return await self._issue_token_pair_for_session(
            user=user,
            device_id=device.id if device is not None else None,
            device_platform=platform,
            device_category=category,
            device_fingerprint_hash=session_service.hash_device_fingerprint(
                payload.device_fingerprint
            ),
            app_version=payload.app_version,
            replace_same_category=self._should_replace_same_category(category),
        )

    async def issue_token_pair(self, user: User) -> tuple[str, str]:
        result = await self._issue_token_pair_for_session(
            user=user,
            device_id=None,
            device_platform="unknown",
            device_category="unknown",
            device_fingerprint_hash=None,
            app_version=None,
            replace_same_category=False,
        )
        return result.access_token, result.refresh_token

    async def refresh_user_tokens(self, refresh_token: str) -> tuple[str, str]:
        session_service = AsyncSessionService(self.db)
        old_session = await session_service.validate_refresh_token(refresh_token)
        user = await self.user_repo.get_by_id(old_session.user_id)

        if user is None or not user.is_active or user.status != "active":
            raise UnauthorizedException(
                message="user is not allowed to refresh token",
                details=[{"field": "refresh_token", "reason": "user is invalid or inactive"}],
            )

        await session_service.revoke_refresh_session(refresh_token, reason="refresh_rotated")
        result = await self._issue_token_pair_for_session(
            user=user,
            device_id=old_session.device_id,
            device_platform=old_session.device_platform,
            device_category=old_session.device_category,
            device_fingerprint_hash=old_session.device_fingerprint_hash,
            app_version=old_session.app_version,
            replace_same_category=False,
        )
        return result.access_token, result.refresh_token

    async def logout_user(self, refresh_token: str, access_token: str) -> None:
        await AsyncSessionService(self.db).revoke_refresh_session(
            refresh_token,
            reason="logout",
        )
        TokenBlacklistService().blacklist_access_token(access_token)

    async def _issue_token_pair_for_session(
        self,
        *,
        user: User,
        device_id: int | None,
        device_platform: str,
        device_category: str,
        device_fingerprint_hash: str | None,
        app_version: str | None,
        replace_same_category: bool,
    ) -> IssuedTokenPair:
        session_service = AsyncSessionService(self.db)
        refresh_token = generate_refresh_token()
        session = await session_service.create_refresh_session(
            user_id=user.id,
            refresh_token=refresh_token,
            device_id=device_id,
            device_platform=device_platform,
            device_category=device_category,
            device_fingerprint_hash=device_fingerprint_hash,
            app_version=app_version,
        )

        access_jti = generate_access_token_jti()
        access_token = create_access_token(
            subject=user.email,
            user_id=user.id,
            is_superuser=user.is_superuser,
            session_id=session.id,
            jti=access_jti,
        )
        session.access_token_jti = access_jti
        await session_service.session_repo.save(session)

        replaced_sessions = []
        if replace_same_category:
            replaced_sessions = await session_service.revoke_same_category_sessions(
                user_id=user.id,
                device_category=device_category,
                replaced_by_session_id=session.id,
            )
            settings = get_settings()
            if settings.auth_blacklist_replaced_access_token:
                blacklist_service = TokenBlacklistService()
                for replaced_session in replaced_sessions:
                    if replaced_session.access_token_jti:
                        blacklist_service.blacklist_access_jti(replaced_session.access_token_jti)

        return IssuedTokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            session_id=session.id,
            device_category=device_category,
            replaced_sessions_count=len(replaced_sessions),
        )

    async def _register_login_device_if_needed(
        self,
        *,
        user: User,
        payload: UserLoginRequest,
    ):
        if not payload.push_token:
            return None
        device_payload = DeviceRegisterRequest(
            platform=payload.platform,
            push_token=payload.push_token,
            device_name=payload.device_name,
        )
        return await AsyncDeviceService(self.db).register_or_update_device(
            user=user,
            payload=device_payload,
        )

    def _should_replace_same_category(self, device_category: str) -> bool:
        settings = get_settings()
        if not settings.auth_single_session_per_device_category_enabled:
            return False
        if device_category == "unknown":
            return settings.auth_single_session_unknown_category_enabled
        return True