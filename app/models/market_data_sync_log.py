"""行情同步日志 Model。

market_data_sync_logs 表记录每一次行情同步的抓取数量、标准化数量、落库数量和错误信息。
它是排查 Provider、网络和数据质量问题的基础观测表。
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MarketDataSyncLog(Base):
    """行情同步日志表。"""

    __tablename__ = "market_data_sync_logs"

    __table_args__ = (
        CheckConstraint(
            "market IN ('US','CN','HK')",
            name="market_data_sync_log_market_valid",
        ),
        CheckConstraint(
            "timeframe IN ('1d','1h','5m')",
            name="market_data_sync_log_timeframe_valid",
        ),
        CheckConstraint(
            "source IN ('mock','baostock','akshare','tushare','alpha_vantage','polygon')",
            name="market_data_sync_log_source_valid",
        ),
        CheckConstraint(
            "adjust_type IN ('none','qfq','hfq')",
            name="market_data_sync_log_adjust_type_valid",
        ),
        CheckConstraint(
            "status IN ('running','success','partial','failed')",
            name="market_data_sync_log_status_valid",
        ),
        CheckConstraint(
            "fetched_count >= 0",
            name="market_data_sync_log_fetched_count_non_negative",
        ),
        CheckConstraint(
            "normalized_count >= 0",
            name="market_data_sync_log_normalized_count_non_negative",
        ),
        CheckConstraint(
            "saved_count >= 0",
            name="market_data_sync_log_saved_count_non_negative",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="market_data_sync_log_duration_ms_non_negative",
        ),
        Index(
            "ix_market_data_sync_logs_symbol_market_timeframe_source_adjust",
            "symbol",
            "market",
            "timeframe",
            "source",
            "adjust_type",
        ),
        Index(
            "ix_market_data_sync_logs_status_started_at",
            "status",
            "started_at",
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
        default="running",
        index=True,
        nullable=False,
    )

    fetched_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
    normalized_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
    saved_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    error_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    duration_ms: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
