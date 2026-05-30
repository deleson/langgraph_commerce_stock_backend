from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    __table_args__ = (
        CheckConstraint(
            "status IN ('active','stale','inactive')",
            name="user_profile_status_valid",
        ),
        CheckConstraint(
            "profile_version >= 1",
            name="user_profile_version_positive",
        ),
        CheckConstraint(
            "generated_from_memory_count >= 0",
            name="user_profile_memory_count_non_negative",
        ),
        CheckConstraint(
            "generated_from_message_count >= 0",
            name="user_profile_message_count_non_negative",
        ),
        CheckConstraint(
            "generated_from_analysis_count >= 0",
            name="user_profile_analysis_count_non_negative",
        ),
        UniqueConstraint(
            "user_id",
            name="uq_user_profiles_user_id",
        ),
        Index(
            "ix_user_profiles_status_refreshed_at",
            "status",
            "refreshed_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="active",
        index=True,
        nullable=False,
    )
    profile_version: Mapped[int] = mapped_column(
        default=1,
        nullable=False,
    )

    summary: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    generated_from_memory_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
    generated_from_message_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
    generated_from_analysis_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=True,
    )

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