"""纸面交易权益快照 Model。

paper_trading_equity_snapshots 表保存虚拟账户每日现金、持仓市值和总权益。
这些快照形成模拟盘权益曲线，不代表真实账户资产。
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PaperTradingEquitySnapshot(Base):
    """纸面交易权益快照表。"""

    __tablename__ = "paper_trading_equity_snapshots"

    __table_args__ = (
        CheckConstraint(
            "cash_balance >= 0",
            name="paper_trading_equity_cash_balance_non_negative",
        ),
        CheckConstraint(
            "position_market_value >= 0",
            name="paper_trading_equity_position_value_non_negative",
        ),
        CheckConstraint(
            "total_equity >= 0",
            name="paper_trading_equity_total_equity_non_negative",
        ),
        UniqueConstraint(
            "account_id",
            "snapshot_date",
            name="uq_paper_trading_equity_snapshots_account_date",
        ),
        # 同一账户同一天只保留一条权益快照，重复 tick 会更新已有快照。
        Index(
            "ix_paper_trading_equity_snapshots_account_date",
            "account_id",
            "snapshot_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # 权益快照归属于虚拟账户。
    account_id: Mapped[int] = mapped_column(
        ForeignKey("paper_trading_accounts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    snapshot_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)

    cash_balance: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    position_market_value: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )
    total_equity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    total_return: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    daily_return: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    max_drawdown: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
