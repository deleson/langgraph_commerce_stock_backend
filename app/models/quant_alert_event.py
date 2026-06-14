"""量化提醒事件 Model。

quant_alert_events 表保存提醒扫描后真正触发的事件。
事件用于通知、列表查询和后续处理状态追踪，不代表交易指令。
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class QuantAlertEvent(Base):
    """量化提醒触发事件表。"""

    __tablename__ = "quant_alert_events"

    __table_args__ = (
        CheckConstraint(
            "rule_type IN ("
            "'strategy_signal',"
            "'strong_strategy_signal',"
            "'strategy_score_threshold',"
            "'price_change',"
            "'volume_spike',"
            "'data_quality'"
            ")",
            name="quant_alert_event_rule_type_valid",
        ),
        CheckConstraint(
            "severity IN ('info','warning','critical')",
            name="quant_alert_event_severity_valid",
        ),
        CheckConstraint(
            "status IN ('triggered','acknowledged','ignored')",
            name="quant_alert_event_status_valid",
        ),
        CheckConstraint(
            "market IN ('US','CN','HK')",
            name="quant_alert_event_market_valid",
        ),
        UniqueConstraint(
            "user_id",
            "dedup_key",
            name="uq_quant_alert_events_user_dedup_key",
        ),
        # dedup_key 防止同一用户在同一触发条件下重复产生事件。
        Index("ix_quant_alert_events_user_event_date", "user_id", "event_date"),
        Index("ix_quant_alert_events_user_status", "user_id", "status"),
        Index("ix_quant_alert_events_user_symbol", "user_id", "market", "symbol"),
        Index("ix_quant_alert_events_user_rule_type", "user_id", "rule_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # 事件必须按用户隔离，避免通知中心泄露其他用户提醒。
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("quant_alert_rules.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    rule_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)

    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        default="triggered",
        nullable=False,
        index=True,
    )

    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    dedup_key: Mapped[str] = mapped_column(String(255), nullable=False)

    trigger_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    notification_id: Mapped[int | None] = mapped_column(nullable=True, index=True)

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
