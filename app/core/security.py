"""认证安全工具。

封装密码强度校验、密码哈希、JWT access token 创建 / 解析、refresh token
生成与哈希逻辑。AuthService 和认证依赖会使用这里的函数。
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import hashlib
import secrets

from jose import JWTError, jwt
from pwdlib import PasswordHash

from app.core.config import get_settings
from app.core.exceptions import BadRequestException, UnauthorizedException
from app.schemas.auth import TokenPayload

password_hash = PasswordHash.recommended()
settings = get_settings()

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def validate_password_strength(password: str) -> None:
    """校验用户密码的基础强度。"""

    if len(password) < MIN_PASSWORD_LENGTH:
        raise BadRequestException(
            message=f"password must be at least {MIN_PASSWORD_LENGTH} characters long",
            details=[{"field": "password", "reason": "password is too short"}],
        )

    if len(password) > MAX_PASSWORD_LENGTH:
        raise BadRequestException(
            message=f"password must be at most {MAX_PASSWORD_LENGTH} characters long",
            details=[{"field": "password", "reason": "password is too long"}],
        )

    if password.isspace():
        raise BadRequestException(
            message="password cannot be blank",
            details=[{"field": "password", "reason": "password cannot contain only whitespace"}],
        )


def hash_password(password: str) -> str:
    """校验并哈希明文密码。"""

    validate_password_strength(password)
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码是否匹配数据库中的密码哈希。"""

    return password_hash.verify(plain_password, hashed_password)


def generate_access_token_jti() -> str:
    """生成 access token 的唯一 jti，便于黑名单和会话追踪。"""

    return uuid4().hex


def create_access_token(
    *,
    subject: str,
    user_id: int,
    is_superuser: bool,
    session_id: int | None = None,
    jti: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """创建 JWT access token。

    session_id 让短期 access token 也能和服务端 user_sessions 绑定。这样当同类
    设备新登录撤销旧 session 后，旧 access token 即使还未自然过期，也会被拒绝。
    """

    expire = datetime.now(UTC) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )

    payload: dict[str, Any] = {
        "sub": subject,
        "user_id": user_id,
        "is_superuser": is_superuser,
        "jti": jti or generate_access_token_jti(),
        "exp": expire,
    }

    if session_id is not None:
        payload["session_id"] = session_id

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> TokenPayload:
    """解析并校验 JWT access token。"""

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return TokenPayload(**payload)
    except JWTError as exc:
        raise UnauthorizedException(
            message="invalid or expired token",
            details=[{"field": "authorization", "reason": "token is invalid or expired"}],
        ) from exc


def generate_refresh_token() -> str:
    """生成 refresh token 明文。"""

    return secrets.token_urlsafe(48)


def hash_refresh_token(refresh_token: str) -> str:
    """对 refresh token 做不可逆哈希后再入库。"""

    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()


def verify_refresh_token(refresh_token: str, refresh_token_hash: str) -> bool:
    """校验客户端提交的 refresh token 是否匹配数据库哈希。"""

    return hash_refresh_token(refresh_token) == refresh_token_hash


def get_refresh_token_expires_at() -> datetime:
    """返回 refresh token 的过期时间。"""

    return datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)