"""AI 额度账户 Model。

ai_quota_accounts 表保存每个用户的日/月调用次数、token 和成本上限。
额度账户用于在真实 LLM 调用前做成本保护。
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AIQuotaAccount(Base):
    """用户 AI 额度账户表。"""

    __tablename__ = "ai_quota_accounts"

    __table_args__ = (
        CheckConstraint(
            "daily_call_limit >= 0",
            name="ai_quota_account_daily_call_limit_non_negative",
        ),
        CheckConstraint(
            "monthly_call_limit >= 0",
            name="ai_quota_account_monthly_call_limit_non_negative",
        ),
        CheckConstraint(
            "daily_token_limit >= 0",
            name="ai_quota_account_daily_token_limit_non_negative",
        ),
        CheckConstraint(
            "monthly_token_limit >= 0",
            name="ai_quota_account_monthly_token_limit_non_negative",
        ),
        CheckConstraint(
            "daily_cost_limit IS NULL OR daily_cost_limit >= 0",
            name="ai_quota_account_daily_cost_limit_non_negative",
        ),
        CheckConstraint(
            "monthly_cost_limit IS NULL OR monthly_cost_limit >= 0",
            name="ai_quota_account_monthly_cost_limit_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # 一个用户只有一份额度账户配置。
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    daily_call_limit: Mapped[int] = mapped_column(
        default=50,
        nullable=False,
    )
    monthly_call_limit: Mapped[int] = mapped_column(
        default=1000,
        nullable=False,
    )

    daily_token_limit: Mapped[int] = mapped_column(
        default=100000,
        nullable=False,
    )
    monthly_token_limit: Mapped[int] = mapped_column(
        default=2000000,
        nullable=False,
    )

    daily_cost_limit: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8),
        nullable=True,
    )
    monthly_cost_limit: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8),
        nullable=True,
    )

    currency: Mapped[str] = mapped_column(
        String(10),
        default="CNY",
        nullable=False,
    )
    timezone: Mapped[str] = mapped_column(
        String(80),
        default="Asia/Shanghai",
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
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
