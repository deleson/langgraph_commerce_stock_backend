"""每日简报 Model。

daily_reports 表保存用户某一天的日报结果、输入快照、AI 润色状态和通知关联。
日报基于历史行情和规则生成，只作为研究参考，不构成投资建议。
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DailyReport(Base):
    """每日简报表。"""

    __tablename__ = "daily_reports"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # 每个日报都属于某个用户，列表和详情查询必须按 user_id 隔离。
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    report_date: Mapped[Date] = mapped_column(
        Date,
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    sections: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    stock_snapshots: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    input_snapshot: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    market_snapshot: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    technical_snapshot: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    strategy_signal_snapshot: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    candidate_snapshot: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    profile_snapshot: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    memory_snapshot: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    ai_used: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    ai_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="not_used",
        index=True,
    )
    ai_usage_log_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_usage_logs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    notification_id: Mapped[int | None] = mapped_column(
        ForeignKey("notifications.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    unavailable_reason: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    warnings: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    disclaimer: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="本每日简报仅基于历史行情、技术指标、策略信号和用户自选股生成，只作为研究参考，不构成投资建议。",
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # 同一用户同一天只保留一份日报，force_rebuild 时更新已有记录。
        UniqueConstraint(
            "user_id",
            "report_date",
            name="uq_daily_reports_user_id_report_date",
        ),
        CheckConstraint(
            "status IN ('generated', 'fallback', 'failed')",
            name="ck_daily_reports_status",
        ),
        CheckConstraint(
            "source IN ('manual', 'api', 'background_task', 'scheduler')",
            name="ck_daily_reports_source",
        ),
        CheckConstraint(
            "ai_status IN ('not_used', 'success', 'quota_blocked', 'llm_error', 'parse_error', 'fallback')",
            name="ck_daily_reports_ai_status",
        ),
        CheckConstraint(
            "unavailable_reason IS NULL OR unavailable_reason IN ('empty_watchlist', 'no_data', 'data_error', 'generation_failed')",
            name="ck_daily_reports_unavailable_reason",
        ),
        Index(
            "ix_daily_reports_user_id_report_date_desc",
            "user_id",
            "report_date",
        ),
    )
