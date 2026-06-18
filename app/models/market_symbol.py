"""股票基础信息 Model。

market_symbols 表保存项目统一后的股票基础信息，面向前端搜索、详情页、
K 线同步状态和后续量化链路使用。不同 Provider 的原始基础信息保存在
market_symbol_sources，避免 Tushare / BaoStock 字段互相覆盖。
"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MarketSymbol(Base):
    """股票基础信息表。"""

    __tablename__ = "market_symbols"

    __table_args__ = (
        # 同一市场下同一股票代码只保留一条基础信息。
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
    list_status: Mapped[str | None] = mapped_column(
        String(30),
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
    data_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    sync_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )
    last_sync_error: Mapped[str | None] = mapped_column(
        String(500),
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
