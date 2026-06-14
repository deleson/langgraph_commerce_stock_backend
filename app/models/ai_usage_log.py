"""AI 调用日志 Model。

ai_usage_logs 表记录每次 LLM 调用的功能类型、状态、token、估算成本和耗时。
它用于成本审计、额度控制和问题排查。
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AIUsageLog(Base):
    """AI 调用日志表。"""

    __tablename__ = "ai_usage_logs"

    __table_args__ = (
        CheckConstraint(
            "feature IN ('stock_analysis','react_reason','react_final_answer','candidate_ai_explanation','daily_report')",
            name="ai_usage_log_feature_valid",
        ),
        CheckConstraint(
            "provider IN ('deepseek')",
            name="ai_usage_log_provider_valid",
        ),
        CheckConstraint(
            "status IN ('success','failed','blocked')",
            name="ai_usage_log_status_valid",
        ),
        CheckConstraint(
            "token_source IN ('provider_usage','estimated','mixed','none')",
            name="ai_usage_log_token_source_valid",
        ),
        CheckConstraint(
            "prompt_tokens >= 0",
            name="ai_usage_log_prompt_tokens_non_negative",
        ),
        CheckConstraint(
            "completion_tokens >= 0",
            name="ai_usage_log_completion_tokens_non_negative",
        ),
        CheckConstraint(
            "total_tokens >= 0",
            name="ai_usage_log_total_tokens_non_negative",
        ),
        CheckConstraint(
            "estimated_cost >= 0",
            name="ai_usage_log_estimated_cost_non_negative",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ai_usage_log_duration_ms_non_negative",
        ),
        Index(
            "ix_ai_usage_logs_user_created_at",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_ai_usage_logs_user_feature_created_at",
            "user_id",
            "feature",
            "created_at",
        ),
        Index(
            "ix_ai_usage_logs_user_status_created_at",
            "user_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_ai_usage_logs_analysis_thread_id",
            "analysis_thread_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # AI 用量按用户归集，额度校验和账单统计都依赖该字段。
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    feature: Mapped[str] = mapped_column(
        String(60),
        index=True,
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(
        String(30),
        default="deepseek",
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="success",
        index=True,
        nullable=False,
    )
    token_source: Mapped[str] = mapped_column(
        String(30),
        default="none",
        nullable=False,
    )

    prompt_tokens: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
    completion_tokens: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )
    total_tokens: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    estimated_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 8),
        default=Decimal("0"),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(10),
        default="CNY",
        nullable=False,
    )

    request_id: Mapped[str | None] = mapped_column(
        String(120),
        index=True,
        nullable=True,
    )
    analysis_thread_id: Mapped[str | None] = mapped_column(
        String(120),
        index=True,
        nullable=True,
    )
    trace_id: Mapped[str | None] = mapped_column(
        String(120),
        index=True,
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    extra: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
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
