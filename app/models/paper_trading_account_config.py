"""纸面交易账户配置 Model。

paper_trading_account_configs 表保存单个虚拟账户的运行开关、仓位限制、手续费和数据质量门控。
这些配置会影响 tick 是否生成虚拟订单，但不会产生真实交易。
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
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


class PaperTradingAccountConfig(Base):
    """纸面交易账户配置表。"""

    __tablename__ = "paper_trading_account_configs"

    __table_args__ = (
        CheckConstraint(
            "max_symbols_per_tick >= 1 AND max_symbols_per_tick <= 500",
            name="paper_trading_account_config_max_symbols_valid",
        ),
        CheckConstraint(
            "max_single_order_cash_ratio > 0 AND max_single_order_cash_ratio <= 1",
            name="paper_trading_account_config_single_order_ratio_valid",
        ),
        CheckConstraint(
            "max_total_position_ratio > 0 AND max_total_position_ratio <= 1",
            name="paper_trading_account_config_total_position_ratio_valid",
        ),
        CheckConstraint(
            "max_position_count >= 1 AND max_position_count <= 500",
            name="paper_trading_account_config_position_count_valid",
        ),
        CheckConstraint(
            "min_order_cash_amount >= 0",
            name="paper_trading_account_config_min_order_cash_non_negative",
        ),
        CheckConstraint(
            "fee_rate >= 0 AND fee_rate <= 0.1",
            name="paper_trading_account_config_fee_rate_valid",
        ),
        CheckConstraint(
            "data_quality_stale_after_days >= 1 AND data_quality_stale_after_days <= 365",
            name="paper_trading_account_config_stale_days_valid",
        ),
        UniqueConstraint(
            "account_id",
            name="uq_paper_trading_account_configs_account_id",
        ),
        # 一个纸面交易账户只有一份当前配置。
        Index(
            "ix_paper_trading_account_configs_enabled",
            "is_enabled",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # 配置随账户删除而删除，避免留下无归属的模拟参数。
    account_id: Mapped[int] = mapped_column(
        ForeignKey("paper_trading_accounts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    max_symbols_per_tick: Mapped[int] = mapped_column(
        default=50,
        nullable=False,
    )

    allow_buy: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    allow_sell: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    max_single_order_cash_ratio: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        default=Decimal("0.10"),
        nullable=False,
    )
    max_total_position_ratio: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        default=Decimal("0.95"),
        nullable=False,
    )
    max_position_count: Mapped[int] = mapped_column(
        default=20,
        nullable=False,
    )
    min_order_cash_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        default=Decimal("100"),
        nullable=False,
    )
    fee_rate: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        default=Decimal("0.0003"),
        nullable=False,
    )

    enforce_data_quality: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    data_quality_stale_after_days: Mapped[int] = mapped_column(
        default=7,
        nullable=False,
    )

    notes: Mapped[str | None] = mapped_column(
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
