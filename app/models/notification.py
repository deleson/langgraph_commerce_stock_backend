"""通知 Model。

notifications 表保存分析完成、日报生成、量化提醒等用户可见通知。
"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Notification(Base):
    """用户通知表。"""

    __tablename__ = "notifications"

    __table_args__ = (
        CheckConstraint(
            "notification_type IN ('system', 'analysis_completed', 'daily_report', 'abnormal_alert', 'quota_warning')",
            name="notification_type_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # 通知必须归属于用户，避免列表接口泄露其他用户消息。
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    related_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_records.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    title: Mapped[str] = mapped_column(String(120), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    notification_type: Mapped[str] = mapped_column(
        String(30),
        default="system",
        nullable=False,
    )

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
