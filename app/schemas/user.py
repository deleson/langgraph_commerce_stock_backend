"""用户资料 Schema。

本文件只描述对外暴露的用户资料和当前用户更新请求。
密码哈希、会话、Token 黑名单等敏感结构不通过这里返回。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserResponse(BaseModel):
    """对外返回的用户资料。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    username: str
    is_active: bool
    is_superuser: bool
    status: str
    created_at: datetime
    updated_at: datetime


class UserUpdateRequest(BaseModel):
    """当前用户资料更新请求体。"""

    username: str | None = Field(default=None, min_length=3, max_length=50)
