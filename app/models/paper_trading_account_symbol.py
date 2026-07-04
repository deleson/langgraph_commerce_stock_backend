"""纸面交易账户固定股票组合 Model。

账户创建时从用户自选股复制股票信息到本表，形成与后续自选股增删无关的快照。
快照不外键关联 watchlist_items，避免用户删除自选股时破坏既有模拟账户的研究区间。
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PaperTradingAccountSymbol(Base):
    """纸面交易账户创建时冻结的股票组合。"""

    __tablename__ = "paper_trading_account_symbols"

    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "market",
            "symbol",
            name="uq_paper_trading_account_symbols_account_market_symbol",
        ),
        CheckConstraint(
            "market IN ('US','CN','HK')",
            name="market_valid",
        ),
        Index(
            "ix_paper_trading_account_symbols_account_order",
            "account_id",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey(
            "paper_trading_accounts.id",
            name="fk_pt_account_symbols_account_id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 仅保留创建时来源 ID 供审计，不建立外键，确保删除自选股不会删除账户快照。
    source_watchlist_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
