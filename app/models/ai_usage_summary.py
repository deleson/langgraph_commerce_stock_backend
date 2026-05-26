from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AIUsageSummary(Base):
    __tablename__ = "ai_usage_summaries"

    __table_args__ = (
        CheckConstraint(
            "period_type IN ('day','month')",
            name="ai_usage_summary_period_type_valid",
        ),
        CheckConstraint(
            "period_end >= period_start",
            name="ai_usage_summary_period_range_valid",
        ),
        CheckConstraint(
            "call_count >= 0",
            name="ai_usage_summary_call_count_non_negative",
        ),
        CheckConstraint(
            "success_count >= 0",
            name="ai_usage_summary_success_count_non_negative",
        ),
        CheckConstraint(
            "failed_count >= 0",
            name="ai_usage_summary_failed_count_non_negative",
        ),
        CheckConstraint(
            "blocked_count >= 0",
            name="ai_usage_summary_blocked_count_non_negative",
        ),
        CheckConstraint(
            "prompt_tokens >= 0",
            name="ai_usage_summary_prompt_tokens_non_negative",
        ),
        CheckConstraint(
            "completion_tokens >= 0",
            name="ai_usage_summary_completion_tokens_non_negative",
        ),
        CheckConstraint(
            "total_tokens >= 0",
            name="ai_usage_summary_total_tokens_non_negative",
        ),
        CheckConstraint(
            "estimated_cost >= 0",
            name="ai_usage_summary_estimated_cost_non_negative",
        ),
        UniqueConstraint(
            "user_id",
            "period_type",
            "period_start",
            name="uq_ai_usage_summaries_user_period",
        ),
        Index(
            "ix_ai_usage_summaries_user_period",
            "user_id",
            "period_type",
            "period_start",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    period_type: Mapped[str] = mapped_column(
        String(20),
        index=True,
        nullable=False,
    )
    period_start: Mapped[date] = mapped_column(
        Date,
        index=True,
        nullable=False,
    )
    period_end: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    call_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
    success_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
    failed_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
    blocked_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    prompt_tokens: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
    completion_tokens: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
    total_tokens: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    estimated_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        default=Decimal("0"),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(10),
        default="CNY",
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