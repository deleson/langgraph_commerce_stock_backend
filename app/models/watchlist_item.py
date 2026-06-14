"""自选股 Model。

watchlist_items 表保存用户关注的股票列表，
是每日简报、量化提醒和纸面交易扫描股票池的重要来源。
"""

from datetime import datetime


from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import Boolean,CheckConstraint,DateTime,ForeignKey,String,UniqueConstraint,func

from app.models.base import Base


class WatchlistItem(Base):
    """用户自选股表。"""

    __tablename__ = "watchlist_items"

    __table_args__ = (
        # 同一用户在同一市场下不能重复添加同一个 symbol。
        UniqueConstraint(
            "user_id",
            "market",
            "symbol",

        name="uq_watchlist_items_user_market_symbol"
        ),
        CheckConstraint(
            "market IN ('US','CN','HK')",
            name="market_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # user_id 是自选股的用户隔离边界，查询时必须限制当前用户。
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    symbol:Mapped[str] = mapped_column(String(20),index=True,nullable=False)
    market:Mapped[str] = mapped_column(String(10),index=True,nullable=False)
    name:Mapped[str | None] = mapped_column(String(100),nullable=True)
    notes:Mapped[str | None] = mapped_column(String(500),nullable=True)

    alert_enabled:Mapped[bool] = mapped_column(Boolean,default=False,nullable=False)

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



