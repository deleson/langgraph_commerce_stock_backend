from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AnalysisReactTrace(Base):
    __tablename__ = "analysis_react_traces"

    __table_args__ = (
        CheckConstraint(
            "action IN ('tool_call','final_answer','error')",
            name="analysis_react_trace_action_valid",
        ),
        CheckConstraint(
            "tool_name IS NULL OR tool_name IN ('get_analysis_record','get_market_overview','get_technical_indicators','get_data_quality','get_user_preference','get_watchlist')",
            name="analysis_react_trace_tool_name_valid",
        ),
        CheckConstraint(
            "step >= 1",
            name="analysis_react_trace_step_positive",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="analysis_react_trace_duration_ms_non_negative",
        ),
        Index(
            "ix_analysis_react_traces_user_thread_step",
            "user_id",
            "analysis_thread_id",
            "step",
        ),
        Index(
            "ix_analysis_react_traces_checkpoint_step",
            "react_graph_checkpoint_id",
            "step",
        ),
        Index(
            "ix_analysis_react_traces_tool_success",
            "tool_name",
            "success",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    analysis_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_records.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    analysis_thread_id: Mapped[str] = mapped_column(
        String(120),
        index=True,
        nullable=False,
    )
    react_graph_checkpoint_id: Mapped[str | None] = mapped_column(
        String(160),
        index=True,
        nullable=True,
    )

    step: Mapped[int] = mapped_column(
        nullable=False,
    )
    action: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )
    tool_name: Mapped[str | None] = mapped_column(
        String(80),
        index=True,
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    tool_input: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    tool_output: Mapped[dict[str, Any] | list[Any] | str | None] = mapped_column(
        JSON,
        nullable=True,
    )
    success: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
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