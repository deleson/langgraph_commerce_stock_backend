from sqlalchemy.orm import Session


from app.core.exceptions import ConflictException,UnauthorizedException
from app.core.security import hash_password,verify_password
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import UserLoginRequest,UserRegisterRequest



class AuthService:
    def __init__(self,db:Session) ->None:
        self.db = db
        self.user_repo = UserRepository(db)

    @staticmethod
    def _normalize_email(email:str) ->str:
        return email.strip().lower()

    @staticmethod
    def _normailze_username(username:str) ->str:
        return username.strip()

    def register_user(self,payload:UserRegisterRequest) -> User:
        email = self._normalize_email(payload.email)
        username = self._normailze_username(payload.username)

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

        return self.user_repo.create(
            email=email,
            username=username,
            hashed_password=hashed_password,
            timezone=payload.timezone,
            risk_preference=payload.risk_preference,
            is_active=True,
            is_superuser=False,
            status="active",
        )

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