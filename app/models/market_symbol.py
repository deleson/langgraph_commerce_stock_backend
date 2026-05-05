from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MarketSymbol(Base):
    __tablename__ = "market_symbols"

    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "market",
            name="uq_market_symbols_symbol_market",
        ),
        CheckConstraint(
            "market IN ('US','CN','HK')",
            name="market_symbol_market_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    symbol: Mapped[str] = mapped_column(
        String(20),
        index=True,
        nullable=False,
    )
    market: Mapped[str] = mapped_column(
        String(10),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    exchange: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )
    provider_symbol: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(
        String(30),
        default="mock",
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