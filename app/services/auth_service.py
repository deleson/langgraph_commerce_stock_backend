"""认证业务 Service。

本文件负责注册、登录、签发 token、刷新 token 和退出登录等认证流程。
Repository 只负责读写用户和会话，密码哈希、JWT、refresh token 轮换和黑名单属于这里的安全业务边界。
"""

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, UnauthorizedException
from app.core.security import create_access_token, generate_refresh_token, hash_password, verify_password
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import UserLoginRequest, UserRegisterRequest
from app.services.session_service import SessionService
from app.services.token_blacklist_service import TokenBlacklistService
from app.repositories.user_preference_repo import UserPreferenceRepository

from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.user_repo import AsyncUserRepository
from app.repositories.user_preference_repo import AsyncUserPreferenceRepository
from app.services.session_service import AsyncSessionService

class AuthService:
    """同步认证业务服务。

    早期同步接口保留该类；当前主要 API 链路更多使用 AsyncAuthService。
    """

    def __init__(self,db:Session) ->None:
        self.db = db
        self.user_repo = UserRepository(db)

    @staticmethod
    def _normalize_email(email:str) ->str:
        return email.strip().lower()

    @staticmethod
    def _normalize_username(username:str) ->str:
        return username.strip()

    def register_user(self,payload:UserRegisterRequest) -> User:
        """注册用户。

        注册时先做邮箱和用户名重复检查，再保存哈希后的密码，并创建默认用户偏好。
        """

        email = self._normalize_email(payload.email)
        username = self._normalize_username(payload.username)

        if self.user_repo.get_by_email(email):
            raise ConflictException(
                message="email already exists",
                details=[{"field":"email","reason":"email already exists"}],
            )

        if self.user_repo.get_by_username(username):
            raise ConflictException(
                message="username already exists",
                details=[{"field":"username","reason":"username already exists"}],
            )

        hashed_password = hash_password(payload.password)

        user = self.user_repo.create(
            email=email,
            username=username,
            hashed_password=hashed_password,
            is_active=True,
            is_superuser=False,
            status="active",
        )
        UserPreferenceRepository(self.db).create_default(user.id)
        return user

    def authenticate_user(self,payload:UserLoginRequest) -> User:
        """校验登录凭证。

        对外统一返回“邮箱或密码错误”，避免暴露具体是邮箱不存在还是密码错误。
        """

        email = self._normalize_email(payload.email)
        user  = self.user_repo.get_by_email(email)

        if user is None:
            raise UnauthorizedException(
                message="invalid email or password",
                details=[{"field":"email","reason":"credentials are invalid"}],
            )

        if not verify_password(payload.password,user.hashed_password):
            raise UnauthorizedException(
                message="invalid email or password",
                details=[{"field":"password","reason":"credentials are invalid"}]
            )

        if not user.is_active or user.status !="active":
            raise UnauthorizedException(
                message="user is not allowed to sign in",
                details=[{"field":"status","reason":"user is inactive or suspended"}]
            )
        return user


    def issue_token_pair(self, user: User) -> tuple[str, str]:
        """签发 access token 和 refresh token。

        access token 用于短期访问接口，refresh token 会创建服务端会话，便于后续撤销。
        """

        access_token = create_access_token(
            subject=user.email,
            user_id=user.id,
            is_superuser=user.is_superuser,
        )
        refresh_token = generate_refresh_token()
        SessionService(self.db).create_refresh_session(
            user_id=user.id,
            refresh_token=refresh_token,
        )
        return access_token, refresh_token

    def refresh_user_tokens(self,refresh_token:str) -> tuple[str,str]:
        """使用 refresh token 换取新 token 对。

        旧 refresh token 会被撤销，避免同一个 refresh token 被长期重复使用。
        """

        session = SessionService(self.db).validate_refresh_token(refresh_token)
        user = self.user_repo.get_by_id(session.user_id)

        if user is None or not user.is_active or user.status !="active":
            raise UnauthorizedException(
                message="user is not allow to refresh token",
                details=[{"field":"refresh_token","reason":"user is invalid or inactive"}]
            )

        SessionService(self.db).revoke_refresh_session(refresh_token)
        return self.issue_token_pair(user)


    def logout_user(self,refresh_token:str,access_token:str) -> None:
        """退出登录。

        refresh token 通过会话撤销，access token 通过 Redis 黑名单提前失效。
        """

        SessionService(self.db).revoke_refresh_session(refresh_token)
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
        """注册用户并创建默认偏好。

        密码只保存哈希，不保存明文；默认偏好让后续日报、提醒、自选股等模块有稳定初始配置。
        """

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

        hashed_password = hash_password(payload.password)

        user = await self.user_repo.create(
            email=email,
            username=username,
            hashed_password=hashed_password,
            is_active=True,
            is_superuser=False,
            status="active",
        )

        await AsyncUserPreferenceRepository(self.db).create_default(user.id)
        return user

    async def authenticate_user(self, payload: UserLoginRequest) -> User:
        """校验登录凭证和用户状态。"""

        email = self._normalize_email(payload.email)
        user = await self.user_repo.get_by_email(email)

        if user is None:
            raise UnauthorizedException(
                message="invalid email or password",
                details=[{"field": "email", "reason": "credentials are invalid"}],
            )

        if not verify_password(payload.password, user.hashed_password):
            raise UnauthorizedException(
                message="invalid email or password",
                details=[{"field": "password", "reason": "credentials are invalid"}],
            )

        if not user.is_active or user.status != "active":
            raise UnauthorizedException(
                message="user is not allowed to sign in",
                details=[{"field": "status", "reason": "user is inactive or suspended"}],
            )

        return user

    async def issue_token_pair(self, user: User) -> tuple[str, str]:
        """签发 access token 和 refresh token，并保存 refresh 会话。"""

        access_token = create_access_token(
            subject=user.email,
            user_id=user.id,
            is_superuser=user.is_superuser,
        )
        refresh_token = generate_refresh_token()

        await AsyncSessionService(self.db).create_refresh_session(
            user_id=user.id,
            refresh_token=refresh_token,
        )

        return access_token, refresh_token

    async def refresh_user_tokens(self, refresh_token: str) -> tuple[str, str]:
        """刷新用户 token。

        refresh token 必须先通过会话校验，再撤销旧会话并签发新 token 对。
        """

        session = await AsyncSessionService(self.db).validate_refresh_token(refresh_token)
        user = await self.user_repo.get_by_id(session.user_id)

        if user is None or not user.is_active or user.status != "active":
            raise UnauthorizedException(
                message="user is not allowed to refresh token",
                details=[
                    {
                        "field": "refresh_token",
                        "reason": "user is invalid or inactive",
                    }
                ],
            )

        await AsyncSessionService(self.db).revoke_refresh_session(refresh_token)
        return await self.issue_token_pair(user)

    async def logout_user(self, refresh_token: str, access_token: str) -> None:
        """退出登录并使当前 token 组合失效。"""

        await AsyncSessionService(self.db).revoke_refresh_session(refresh_token)
        TokenBlacklistService().blacklist_access_token(access_token)
