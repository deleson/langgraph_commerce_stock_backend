from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
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


class MarketCandle(Base):
    __tablename__ = "market_candles"

    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "market",
            "timeframe",
            "candle_time",
            "source",
            "adjust_type",
            name="uq_market_candles_symbol_market_timeframe_time_source_adjust",
        ),
        CheckConstraint(
            "market IN ('US','CN','HK')",
            name="market_candle_market_valid",
        ),
        CheckConstraint(
            "timeframe IN ('1d','1h','5m')",
            name="market_candle_timeframe_valid",
        ),
        CheckConstraint(
            "open_price >= 0",
            name="market_candle_open_price_non_negative",
        ),
        CheckConstraint(
            "high_price >= 0",
            name="market_candle_high_price_non_negative",
        ),
        CheckConstraint(
            "low_price >= 0",
            name="market_candle_low_price_non_negative",
        ),
        CheckConstraint(
            "close_price >= 0",
            name="market_candle_close_price_non_negative",
        ),
        CheckConstraint(
            "high_price >= low_price",
            name="market_candle_high_gte_low",
        ),
        CheckConstraint(
            "volume >= 0",
            name="market_candle_volume_non_negative",
        ),
        Index(
            "ix_market_candles_symbol_market_timeframe_time",
            "symbol",
            "market",
            "timeframe",
            "candle_time",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    symbol_id: Mapped[int | None] = mapped_column(
        ForeignKey("market_symbols.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
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
    timeframe: Mapped[str] = mapped_column(
        String(10),
        index=True,
        nullable=False,
    )
    candle_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=False,
    )

    open_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )
    high_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )
    low_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )
    close_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )
    volume: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )
    amount: Mapped[Decimal | None] = mapped_column(
        Numeric(24, 4),
        nullable=True,
    )

    source: Mapped[str] = mapped_column(
        String(30),
        default="mock",
        nullable=False,
    )
    is_adjusted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    adjust_type: Mapped[str] = mapped_column(
        String(10),
        default="none",
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