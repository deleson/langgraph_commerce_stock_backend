"""用户设备 Model。

devices 表保存 Web / App 设备标识、平台和推送 token，
用于后续通知推送和设备管理。
"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Device(Base):
    """用户设备表。"""

    __tablename__ = "devices"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "platform",
            "push_token",
            name="devices_user_platform_push_token_unique",
        ),
        CheckConstraint(
            "platform IN ('ios', 'android', 'web', 'unknown')",
            name="device_platform_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    platform: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    push_token: Mapped[str] = mapped_column(String(500), nullable=False)
    device_name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
