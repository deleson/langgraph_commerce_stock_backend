"""通知中心 Schema。

通知用于承载分析完成、日报生成、量化提醒触发等用户可见事件。
本文件只定义通知数据结构，不负责具体通知生成逻辑。
"""

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
    """创建通知的内部请求结构。"""

    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1)
    notification_type: NotificationType = "system"
    related_record_id: int | None = None


class NotificationResponse(BaseModel):
    """通知响应体。"""

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
