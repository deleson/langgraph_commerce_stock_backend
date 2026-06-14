"""行情同步状态 Model。

market_data_sync_statuses 表记录每只股票、时间周期、数据源和复权类型的最新同步状态。
它用于判断数据是否已经同步、最近一次成功或失败发生在什么时候。
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MarketDataSyncStatus(Base):
    """行情同步状态表。"""

    __tablename__ = "market_data_sync_statuses"

    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "market",
            "timeframe",
            "source",
            "adjust_type",
            name="uq_market_data_sync_status_identity",
        ),
        # 常用查询路径：按股票、市场和周期查看同步状态。
        CheckConstraint(
            "market IN ('US','CN','HK')",
            name="market_data_sync_status_market_valid",
        ),
        CheckConstraint(
            "timeframe IN ('1d','1h','5m')",
            name="market_data_sync_status_timeframe_valid",
        ),
        CheckConstraint(
            "source IN ('mock','baostock','akshare','tushare','alpha_vantage','polygon')",
            name="market_data_sync_status_source_valid",
        ),
        CheckConstraint(
            "adjust_type IN ('none','qfq','hfq')",
            name="market_data_sync_status_adjust_type_valid",
        ),
        CheckConstraint(
            "status IN ('never_synced','success','partial','failed')",
            name="market_data_sync_status_status_valid",
        ),
        CheckConstraint(
            "candle_count >= 0",
            name="market_data_sync_status_candle_count_non_negative",
        ),
        Index(
            "ix_market_data_sync_status_symbol_market_timeframe",
            "symbol",
            "market",
            "timeframe",
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
    source: Mapped[str] = mapped_column(
        String(30),
        index=True,
        nullable=False,
    )
    adjust_type: Mapped[str] = mapped_column(
        String(10),
        default="none",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="never_synced",
        index=True,
        nullable=False,
    )

    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    earliest_candle_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    latest_candle_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    candle_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
    last_error_message: Mapped[str | None] = mapped_column(
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
