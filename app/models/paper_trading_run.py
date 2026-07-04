"""纸面交易运行记录 Model。

paper_trading_runs 表保存每一次 tick 的请求快照、配置快照、信号快照、执行快照和持仓快照。
它用于审计一次模拟盘推进为什么生成或跳过订单。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PaperTradingRun(Base):
    """纸面交易 tick 运行记录表。"""

    __tablename__ = "paper_trading_runs"

    __table_args__ = (
        CheckConstraint(
            "status IN ('running','completed','skipped','failed')",
            name="paper_trading_run_status_valid",
        ),
        CheckConstraint(
            "source IN ('manual','api','background_task','scheduler')",
            name="paper_trading_run_source_valid",
        ),
        CheckConstraint(
            "unavailable_reason IS NULL OR unavailable_reason IN ("
            "'no_account',"
            "'no_watchlist',"
            "'no_universe',"
            "'no_data',"
            "'data_error',"
            "'market_closed',"
            "'tick_failed'"
            ")",
            name="paper_trading_run_unavailable_reason_valid",
        ),
        CheckConstraint(
            "scanned_count >= 0",
            name="paper_trading_run_scanned_count_non_negative",
        ),
        CheckConstraint(
            "actionable_count >= 0",
            name="paper_trading_run_actionable_count_non_negative",
        ),
        CheckConstraint(
            "order_count >= 0",
            name="paper_trading_run_order_count_non_negative",
        ),
        CheckConstraint(
            "trade_count >= 0",
            name="paper_trading_run_trade_count_non_negative",
        ),
        CheckConstraint(
            "skipped_count >= 0",
            name="paper_trading_run_skipped_count_non_negative",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="paper_trading_run_duration_ms_non_negative",
        ),
        Index(
            "ix_paper_trading_runs_account_status_started_at",
            "account_id",
            "status",
            "started_at",
        ),
        Index(
            "ix_paper_trading_runs_account_source_started_at",
            "account_id",
            "source",
            "started_at",
        ),
        Index(
            "ix_paper_trading_runs_equity_snapshot",
            "equity_snapshot_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # 每次运行记录都归属于一个虚拟账户。
    account_id: Mapped[int] = mapped_column(
        ForeignKey("paper_trading_accounts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    equity_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("paper_trading_equity_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="running",
        index=True,
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(30),
        default="api",
        index=True,
        nullable=False,
    )
    unavailable_reason: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    scanned_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
    actionable_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
    order_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
    trade_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
    skipped_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    request_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    account_config_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    signal_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    execution_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    position_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    warnings: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    errors: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
