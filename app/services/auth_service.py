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
        SessionService(self.db).revoke_refresh_session(refresh_token)
        TokenBlacklistService().blacklist_access_token(access_token)




class AsyncAuthService:
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
        await AsyncSessionService(self.db).revoke_refresh_session(refresh_token)
        TokenBlacklistService().blacklist_access_token(access_token)