"""用户设备 Schema。

设备信息用于后续 Web / App 推送和设备管理。
当前 Schema 只保存设备标识、平台和启用状态，不处理真实推送发送。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


DevicePlatform = Literal["ios", "android", "web", "unknown"]


class DeviceRegisterRequest(BaseModel):
    """设备注册或更新请求体。"""

    platform: DevicePlatform
    push_token: str = Field(min_length=1, max_length=500)
    device_name: str | None = Field(default=None, max_length=120)

    @field_validator("platform", mode="before")
    @classmethod
    def normalize_platform(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("push_token", "device_name", mode="before")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip()
        return value


class DeviceResponse(BaseModel):
    """设备响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    push_token: str
    device_name: str | None
    is_active: bool
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime
