from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PaperTradingAccount(Base):
    __tablename__ = "paper_trading_accounts"

    __table_args__ = (
        CheckConstraint(
            "status IN ('active','paused','closed')",
            name="paper_trading_account_status_valid",
        ),
        CheckConstraint(
            "initial_cash > 0",
            name="paper_trading_account_initial_cash_positive",
        ),
        CheckConstraint(
            "cash_balance >= 0",
            name="paper_trading_account_cash_balance_non_negative",
        ),
        CheckConstraint(
            "currency IN ('CNY','USD','HKD')",
            name="paper_trading_account_currency_valid",
        ),
        Index("ix_paper_trading_accounts_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)

    initial_cash: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )
    cash_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(8),
        default="CNY",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        index=True,
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