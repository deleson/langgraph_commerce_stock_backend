from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PaperTradingOrder(Base):
    __tablename__ = "paper_trading_orders"

    __table_args__ = (
        CheckConstraint(
            "market IN ('US','CN','HK')",
            name="paper_trading_order_market_valid",
        ),
        CheckConstraint(
            "side IN ('buy','sell')",
            name="paper_trading_order_side_valid",
        ),
        CheckConstraint(
            "status IN ('pending','filled','cancelled','rejected','skipped')",
            name="paper_trading_order_status_valid",
        ),
        CheckConstraint(
            "signal_source IN ('strategy_signal','quant_alert','manual')",
            name="paper_trading_order_signal_source_valid",
        ),
        CheckConstraint(
            "planned_quantity > 0",
            name="paper_trading_order_planned_quantity_positive",
        ),
        CheckConstraint(
            "planned_price IS NULL OR planned_price > 0",
            name="paper_trading_order_planned_price_positive",
        ),
        CheckConstraint(
            "filled_quantity >= 0",
            name="paper_trading_order_filled_quantity_non_negative",
        ),
        Index("ix_paper_trading_orders_account_status", "account_id", "status"),
        Index(
            "ix_paper_trading_orders_account_symbol",
            "account_id",
            "market",
            "symbol",
        ),
        Index(
            "ix_paper_trading_orders_account_created_at",
            "account_id",
            "created_at",
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

    side: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        index=True,
        nullable=False,
    )

    planned_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    planned_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    filled_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        default=Decimal("0"),
        nullable=False,
    )
    filled_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)

    signal_source: Mapped[str] = mapped_column(String(40), nullable=False)
    signal_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    reason: Mapped[str] = mapped_column(Text, nullable=False)

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