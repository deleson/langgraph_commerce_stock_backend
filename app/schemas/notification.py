from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


NotificationType = Literal[
    "system",
    "analysis_completed",
    "daily_report",
    "abnormal_alert",
    "quota_warning",
]


class NotificationCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1)
    notification_type: NotificationType = "system"
    related_record_id: int | None = None


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    notification_type: str
    related_record_id: int | None
    is_read: bool
    read_at: datetime | None
    created_at: datetime
    updated_at: datetime