"""认证相关 Schema。

本文件定义注册、登录、刷新 Token、退出登录等接口的数据结构。
密码校验、JWT 签发和会话落库由 Service / Core 层完成。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


DevicePlatform = Literal["ios", "android", "web", "unknown"]


class UserRegisterRequest(BaseModel):
    """用户注册请求体。"""

    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=3, max_length=128)


class UserLoginRequest(BaseModel):
    """用户登录请求体。

    设备字段用于服务端做同类设备单会话控制。为兼容旧客户端，设备信息默认
    为 unknown；Android / Web 新客户端应显式传 platform 和 device_fingerprint。
    """

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    platform: DevicePlatform = "unknown"
    device_fingerprint: str | None = Field(default=None, max_length=255)
    device_name: str | None = Field(default=None, max_length=120)
    push_token: str | None = Field(default=None, max_length=500)
    app_version: str | None = Field(default=None, max_length=50)

    @field_validator("platform", mode="before")
    @classmethod
    def normalize_platform(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().lower() or "unknown"
        return value

    @field_validator(
        "device_fingerprint",
        "device_name",
        "push_token",
        "app_version",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value


class TokenPayload(BaseModel):
    """JWT 解码后的业务载荷。"""

    sub: str
    user_id: int
    is_superuser: bool = False
    jti: str
    exp: int
    session_id: int | None = None


class TokenResponse(BaseModel):
    """单个访问 Token 响应。"""

    access_token: str
    token_type: str = "bearer"


class AuthenticatedUser(BaseModel):
    """认证成功后的当前用户摘要。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    username: str
    is_active: bool
    is_superuser: bool


class RefreshTokenRequest(BaseModel):
    """刷新访问 Token 的请求体。"""

    refresh_token: str


class LogoutRequest(BaseModel):
    """退出登录请求体。"""

    refresh_token: str


class TokenPairResponse(BaseModel):
    """访问 Token 与刷新 Token 的成对响应。"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    session_id: int | None = None
    device_category: str | None = None
    replaced_sessions_count: int = 0