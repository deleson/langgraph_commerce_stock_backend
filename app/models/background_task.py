"""后台任务 Model。

background_tasks 表记录 API 或调度器提交的异步任务、Celery task id、状态、结果和错误信息。
它让用户可以追踪 queued / running / success / failed 等任务生命周期。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BackgroundTask(Base):
    """后台任务表。"""

    __tablename__ = "background_tasks"

    __table_args__ = (
        CheckConstraint(
            "task_type IN ("
            "'market_data_sync',"
            "'watchlist_candle_sync',"
            "'stock_analysis_async',"
            "'candidate_scoring_async',"
            "'candidate_ai_explanation_async',"
            "'user_profile_refresh',"
            "'user_memory_embedding_rebuild',"
            "'daily_report',"
            "'alert_scan',"
            "'paper_trading_tick'"
            ")",
            name="background_task_type_valid",
        ),
        CheckConstraint(
            "status IN ('pending','queued','running','success','failed','retrying','cancelled')",
            name="background_task_status_valid",
        ),
        CheckConstraint(
            "priority IN ('low','normal','high')",
            name="background_task_priority_valid",
        ),
        CheckConstraint(
            "source IN ('api','system','scheduler')",
            name="background_task_source_valid",
        ),
        CheckConstraint(
            "retry_count >= 0",
            name="background_task_retry_count_non_negative",
        ),
        CheckConstraint(
            "max_retries >= 0",
            name="background_task_max_retries_non_negative",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="background_task_duration_ms_non_negative",
        ),
        Index(
            "ix_background_tasks_user_status_created_at",
            "user_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_background_tasks_type_status_created_at",
            "task_type",
            "status",
            "created_at",
        ),
        Index(
            "ix_background_tasks_status_scheduled_for",
            "status",
            "scheduled_for",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # 系统任务可以没有 user_id；用户任务必须带 user_id 才能做列表隔离。
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    task_type: Mapped[str] = mapped_column(
        String(80),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        index=True,
        nullable=False,
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        default="normal",
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(30),
        default="api",
        nullable=False,
    )

    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    celery_task_id: Mapped[str | None] = mapped_column(
        String(160),
        unique=True,
        index=True,
        nullable=True,
    )

    retry_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
    max_retries: Mapped[int] = mapped_column(
        default=3,
        nullable=False,
    )

    scheduled_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=True,
    )
    queued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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
