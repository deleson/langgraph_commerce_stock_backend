"""认证相关 Schema。

本文件定义注册、登录、刷新 Token、退出登录等接口的数据结构。
密码校验、密码哈希、JWT 签发和会话落库由 Service / Core 层完成。
"""

from pydantic import BaseModel,ConfigDict,EmailStr,Field

class UserRegisterRequest(BaseModel):
    """用户注册请求体。

    这里只定义用户提交的邮箱、用户名和密码格式，不保存密码哈希。
    """

    email:EmailStr
    username: str = Field(min_length=3,max_length=50)
    password: str = Field(min_length=3,max_length=128)


class UserLoginRequest(BaseModel):
    """用户登录请求体。"""

    email:EmailStr
    password:str = Field(min_length=8,max_length=128)


class TokenPayload(BaseModel):
    """JWT 解码后的业务载荷。

    API 鉴权依赖该载荷识别当前用户，并继续检查会话和用户状态。
    """

    sub:str
    user_id: int
    is_superuser: bool = False
    jti: str
    exp: int

class TokenResponse(BaseModel):
    """单个访问 Token 响应。"""

    access_token:str
    token_type:str = "bearer"

class AuthenticatedUser(BaseModel):
    """认证成功后的当前用户摘要。

    响应中不包含 hashed_password 等敏感字段。
    """

    model_config = ConfigDict(from_attributes=True)

    id:int
    email:EmailStr
    username:str
    is_active:bool
    is_superuser:bool




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
