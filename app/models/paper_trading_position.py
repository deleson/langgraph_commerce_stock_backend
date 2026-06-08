from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PaperTradingPosition(Base):
    __tablename__ = "paper_trading_positions"

    __table_args__ = (
        CheckConstraint(
            "market IN ('US','CN','HK')",
            name="paper_trading_position_market_valid",
        ),
        CheckConstraint(
            "quantity >= 0",
            name="paper_trading_position_quantity_non_negative",
        ),
        CheckConstraint(
            "avg_cost >= 0",
            name="paper_trading_position_avg_cost_non_negative",
        ),
        CheckConstraint(
            "market_value >= 0",
            name="paper_trading_position_market_value_non_negative",
        ),
        UniqueConstraint(
            "account_id",
            "market",
            "symbol",
            name="uq_paper_trading_positions_account_market_symbol",
        ),
        Index(
            "ix_paper_trading_positions_account_symbol",
            "account_id",
            "market",
            "symbol",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("paper_trading_accounts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    market: Mapped[str] = mapped_column(String(16), index=True, nullable=False)

    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    last_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    market_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unrealized_return: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 8),
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