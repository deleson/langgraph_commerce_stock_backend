from datetime import UTC,datetime,timedelta
from typing import Any

from jose import JWTError,jwt
from pwdlib import PasswordHash


from app.core.config import get_settings
from app.core.exceptions import BadRequestException,UnauthorizedException
from app.schemas.auth import TokenPayload

import hashlib
import secrets

from uuid import uuid4

password_hash = PasswordHash.recommended()
settings = get_settings()

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128



def validate_password_strength(password:str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise BadRequestException(
            message=f"password must be at least {MIN_PASSWORD_LENGTH} characters long",
            details=[{"field":"password","reason":"password is too short"}]
        )

    if len(password) > MAX_PASSWORD_LENGTH:
        raise BadRequestException(
            message=f"password must be at most {MAX_PASSWORD_LENGTH} characters long",
            details=[{"field":"password","reason":"password is too long"}]
        )

    if password.isspace():
        raise BadRequestException(
            message="password cannot be blank",
            details=[{"field": "password", "reason": "password cannot contain only whitespace"}],
        )


def hash_password(password:str) -> str:
    validate_password_strength(password)
    return password_hash.hash(password)

def verify_password(plain_password:str,hashed_password:str) -> bool:
    return password_hash.verify(plain_password,hashed_password)


def create_access_token(
        *,
        subject:str,
        user_id:int,
        is_superuser:bool,
        expires_delta:timedelta | None = None,
) -> str:
    expire = datetime.now(UTC) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )

    payload:dict[str,Any] = {
        "sub": subject,
        "user_id": user_id,
        "is_superuser": is_superuser,
        "jti":uuid4().hex,
        "exp":expire,
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,

    )


def decode_access_token(token:str) -> TokenPayload:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        return TokenPayload(**payload)
    except JWTError as exc:
        raise UnauthorizedException(
            message = "invalide or expired token",
            details=[{"field":"authorization","reason":"token is invalid or expired"}]
        ) from exc



def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(refresh_token: str) -> str:
    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()


def verify_refresh_token(refresh_token: str, refresh_token_hash: str) -> bool:
    return hash_refresh_token(refresh_token) == refresh_token_hash


def get_refresh_token_expires_at() -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)