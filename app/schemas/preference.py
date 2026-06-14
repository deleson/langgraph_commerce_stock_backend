"""用户偏好 Schema。

用户偏好影响 AI 分析口径、候选评分偏好、日报和提醒默认行为。
这里仅定义字段结构，具体默认值和创建逻辑由 Service 层负责。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


RiskPreference = Literal["conservative", "balanced", "aggressive"]


class UserPreferenceUpdateRequest(BaseModel):
    """当前用户偏好更新请求体。"""

    risk_preference: RiskPreference | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=50)
    daily_report_enabled: bool | None = None
    abnormal_alert_enabled: bool | None = None
    default_watchlist_alert_enabled: bool | None = None

    @field_validator("timezone", mode="before")
    @classmethod
    def normalize_timezone(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip()
        return value


class UserPreferenceResponse(BaseModel):
    """当前用户偏好响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    risk_preference: str
    timezone: str
    daily_report_enabled: bool
    abnormal_alert_enabled: bool
    default_watchlist_alert_enabled: bool
    created_at: datetime
    updated_at: datetime
