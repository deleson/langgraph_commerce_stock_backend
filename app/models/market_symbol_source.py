"""Provider 股票基础信息来源表。

market_symbol_sources 保存 Tushare、BaoStock 等 Provider 返回的原始基础信息
和哈希指纹。统一表 market_symbols 只保存当前业务选择后的展示数据，避免不同
Provider 字段格式差异导致互相覆盖。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MarketSymbolSource(Base):
    """单个 Provider 维度的股票基础信息缓存。"""

    __tablename__ = "market_symbol_sources"

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "market",
            "symbol",
            name="uq_market_symbol_sources_provider_market_symbol",
        ),
        CheckConstraint(
            "market IN ('US','CN','HK')",
            name="market_symbol_sources_market_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    symbol: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    market: Mapped[str] = mapped_column(String(10), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    provider_symbol: Mapped[str | None] = mapped_column(String(50), nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    exchange: Mapped[str | None] = mapped_column(String(30), nullable=True)
    list_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    raw_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sync_status: Mapped[str] = mapped_column(String(30), default="success", nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_sync_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

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
