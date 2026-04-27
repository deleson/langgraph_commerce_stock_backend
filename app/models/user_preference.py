from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserPreference(Base):
    __tablename__ = "user_preferences"

    __table_args__ = (
        CheckConstraint(
            "risk_preference IN ('conservative', 'balanced', 'aggressive')",
            name="risk_preference_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    risk_preference: Mapped[str] = mapped_column(
        String(20),
        default="balanced",
        nullable=False,
    )
    timezone: Mapped[str] = mapped_column(
        String(50),
        default="Asia/Shanghai",
        nullable=False,
    )

    daily_report_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    abnormal_alert_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_watchlist_alert_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
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