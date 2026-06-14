"""量化提醒规则 Model。

quant_alert_rules 表保存用户配置的提醒规则，例如策略信号、分数阈值、涨跌幅和数据质量。
规则只产生研究提醒，不会触发真实交易。
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class QuantAlertRule(Base):
    """量化提醒规则表。"""

    __tablename__ = "quant_alert_rules"

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
            name="quant_alert_rule_type_valid",
        ),
        CheckConstraint(
            "status IN ('active','inactive')",
            name="quant_alert_rule_status_valid",
        ),
        CheckConstraint(
            "severity IN ('info','warning','critical')",
            name="quant_alert_rule_severity_valid",
        ),
        CheckConstraint(
            "trigger_direction IS NULL OR trigger_direction IN ('above','below','equal','changed')",
            name="quant_alert_rule_trigger_direction_valid",
        ),
        CheckConstraint(
            "market IS NULL OR market IN ('US','CN','HK')",
            name="quant_alert_rule_market_valid",
        ),
        CheckConstraint(
            "cooldown_minutes >= 0",
            name="quant_alert_rule_cooldown_non_negative",
        ),
        UniqueConstraint(
            "user_id",
            "rule_type",
            "market",
            "symbol",
            name="uq_quant_alert_rules_user_type_market_symbol",
        ),
        # 规则查询最常按用户、状态、类型或股票过滤。
        Index("ix_quant_alert_rules_user_status", "user_id", "status"),
        Index("ix_quant_alert_rules_user_type", "user_id", "rule_type"),
        Index("ix_quant_alert_rules_user_symbol", "user_id", "market", "symbol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # 提醒规则属于用户私有配置，不能跨用户读取或执行。
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        nullable=False,
        index=True,
    )

    market: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    severity: Mapped[str] = mapped_column(
        String(20),
        default="warning",
        nullable=False,
    )
    trigger_direction: Mapped[str | None] = mapped_column(String(20), nullable=True)
    threshold_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)

    cooldown_minutes: Mapped[int] = mapped_column(default=1440, nullable=False)
    enabled_notification: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_config: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
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
