"""用户会话 Model。

user_sessions 表保存 refresh token 的哈希、撤销状态、过期时间和登录设备上下文，
用于支持刷新 Token、退出登录、同类设备单会话控制和会话失效审计。
"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserSession(Base):
    """用户刷新 Token 会话表。"""

    __tablename__ = "user_sessions"

    __table_args__ = (
        CheckConstraint(
            "device_platform IN ('ios','android','web','unknown')",
            name="user_session_device_platform_valid",
        ),
        CheckConstraint(
            "device_category IN ('mobile','web','unknown')",
            name="user_session_device_category_valid",
        ),
        CheckConstraint(
            "revoked_reason IS NULL OR revoked_reason IN ("
            "'logout','refresh_rotated','replaced_by_same_category_login',"
            "'admin_revoked','expired'"
            ")",
            name="user_session_revoked_reason_valid",
        ),
        Index(
            "ix_user_sessions_user_category_revoked",
            "user_id",
            "device_category",
            "is_revoked",
        ),
        Index(
            "ix_user_sessions_access_token_jti",
            "access_token_jti",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # user_id 是会话归属边界，用户删除时会话也应级联删除。
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    device_id: Mapped[int | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    device_platform: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    device_category: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)
    device_fingerprint_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    access_token_jti: Mapped[str | None] = mapped_column(String(64), nullable=True)

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    replaced_by_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
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