from datetime import datetime


from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import Boolean,CheckConstraint,DateTime,ForeignKey,String,UniqueConstraint,func

from app.models.base import Base


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    __table_args__ = (
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



