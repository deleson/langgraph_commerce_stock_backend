from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint,DateTime,ForeignKey,JSON,String,Text,func
from sqlalchemy.orm import Mapped,mapped_column

from app.models.base import Base


class AnalysisRecord(Base):
    __tablename__ = "analysis_records"

    __table_args__ = (
        CheckConstraint(
            "market IN ('US','CN','HK')",
            name="analysis_market_valid",
        ),
        CheckConstraint(
            "analysis_type IN ('stock_basic','daily_report','abnormal_alert','simulation')",
            name="analysis_type_valid",
        ),
        CheckConstraint(
            "status IN ('pending','running','completed','failed')",
            name="analysis_status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id:Mapped[int] = mapped_column(
        ForeignKey("users.id",ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    symbol: Mapped[str] = mapped_column(String(20),index=True,nullable=False)
    market: Mapped[str] = mapped_column(String(10),index=True,nullable=False)

    analysis_type: Mapped[str] = mapped_column(
        String(30),
        default="stock_basic",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="completed",
        nullable=False,
    )

    summary: Mapped[str | None] = mapped_column(String(500),nullable=True)
    result_snapshot: Mapped[dict[str,Any] | None] = mapped_column(JSON,nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text,nullable=True)

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
