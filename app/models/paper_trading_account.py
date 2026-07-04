"""纸面交易账户 Model。

paper_trading_accounts 表保存用户的虚拟账户、初始资金和当前现金余额。
该账户只用于模拟盘，不连接券商，也不会真实下单。
"""

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
    """纸面交易虚拟账户表。"""

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

    # 虚拟账户归属于用户，所有纸面交易子资源都从 account 继续隔离。
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

    # 账户关闭后冻结研究区间终点，后续详情以该时间汇总整个模拟周期。
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
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
