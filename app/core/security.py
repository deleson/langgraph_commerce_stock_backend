"""认证安全工具。

该文件封装密码强度校验、密码哈希、JWT access token 创建 / 解析、
refresh token 生成与哈希逻辑。AuthService 和认证依赖会使用这里的函数。

注意：
生产环境的 JWT_SECRET_KEY 必须保密且足够随机；正式公开访问前应配置 HTTPS，
避免 token 在网络传输中被窃取。
"""

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
    """校验用户密码的基础强度。

    当前第一版只做长度和空白密码限制，避免明显弱密码进入哈希流程。
    更严格的复杂度要求可以在后续安全加固阶段补充。
    """

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
    """校验并哈希明文密码。

    数据库只保存哈希后的密码，不能保存用户明文密码。
    """

    validate_password_strength(password)
    return password_hash.hash(password)

def verify_password(plain_password:str,hashed_password:str) -> bool:
    """校验明文密码是否匹配数据库中的密码哈希。"""

    return password_hash.verify(plain_password,hashed_password)


def create_access_token(
        *,
        subject:str,
        user_id:int,
        is_superuser:bool,
        expires_delta:timedelta | None = None,
) -> str:
    """创建 JWT access token。

    access token 用于后续请求鉴权，payload 中包含用户标识、超级用户标记、
    唯一 jti 和过期时间。业务接口通过解析 token 确认当前用户身份。
    """

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
    """解析并校验 JWT access token。

    token 无效、过期或签名不匹配时抛出 UnauthorizedException，由统一异常
    处理器转换为 401 响应。
    """

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
    """生成 refresh token 明文。

    refresh token 只在签发时返回给客户端，服务端数据库保存的是哈希值。
    """

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
