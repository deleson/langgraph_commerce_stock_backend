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


class PaperTradingTrade(Base):
    __tablename__ = "paper_trading_trades"

    __table_args__ = (
        CheckConstraint(
            "market IN ('US','CN','HK')",
            name="paper_trading_trade_market_valid",
        ),
        CheckConstraint(
            "side IN ('buy','sell')",
            name="paper_trading_trade_side_valid",
        ),
        CheckConstraint(
            "filled_quantity > 0",
            name="paper_trading_trade_filled_quantity_positive",
        ),
        CheckConstraint(
            "filled_price > 0",
            name="paper_trading_trade_filled_price_positive",
        ),
        CheckConstraint(
            "trade_value >= 0",
            name="paper_trading_trade_value_non_negative",
        ),
        CheckConstraint(
            "fee_amount >= 0",
            name="paper_trading_trade_fee_non_negative",
        ),
        Index(
            "ix_paper_trading_trades_account_traded_at",
            "account_id",
            "traded_at",
        ),
        Index(
            "ix_paper_trading_trades_account_symbol",
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
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("paper_trading_orders.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    market: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False)

    filled_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    filled_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    trade_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    fee_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        default=Decimal("0"),
        nullable=False,
    )

    traded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )