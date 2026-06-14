"""用户记忆 Model。

user_memories 表保存用户偏好、关注股票、研究习惯和对话中抽取出的长期上下文。
这些记忆只用于增强当前用户的 AI 分析体验，必须按 user_id 隔离。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserMemory(Base):
    """用户长期记忆表。"""

    __tablename__ = "user_memories"

    __table_args__ = (
        CheckConstraint(
            "memory_type IN ("
            "'risk_preference',"
            "'market_interest',"
            "'symbol_interest',"
            "'research_preference',"
            "'risk_focus',"
            "'communication_preference',"
            "'analysis_context_preference',"
            "'feature_usage'"
            ")",
            name="user_memory_type_valid",
        ),
        CheckConstraint(
            "status IN ('active','inactive')",
            name="user_memory_status_valid",
        ),
        CheckConstraint(
            "confidence IN ('low','medium','high')",
            name="user_memory_confidence_valid",
        ),
        CheckConstraint(
            "source_type IN ("
            "'user_preference',"
            "'watchlist',"
            "'analysis_record',"
            "'conversation_message',"
            "'react_trace',"
            "'backtest_request',"
            "'stock_candidate_request',"
            "'manual',"
            "'system'"
            ")",
            name="user_memory_source_type_valid",
        ),
        CheckConstraint(
            "weight >= 1 AND weight <= 100",
            name="user_memory_weight_range",
        ),
        Index(
            "ix_user_memories_user_status_created_at",
            "user_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_user_memories_user_type_status",
            "user_id",
            "memory_type",
            "status",
        ),
        Index(
            "ix_user_memories_user_source",
            "user_id",
            "source_type",
            "source_id",
        ),
        Index(
            "ix_user_memories_user_confidence",
            "user_id",
            "confidence",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # 记忆属于用户隐私上下文，任何查询都必须限制当前用户。
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    memory_type: Mapped[str] = mapped_column(
        String(60),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="active",
        index=True,
        nullable=False,
    )
    confidence: Mapped[str] = mapped_column(
        String(30),
        default="medium",
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    summary: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    source_type: Mapped[str] = mapped_column(
        String(60),
        index=True,
        nullable=False,
    )
    source_id: Mapped[int | None] = mapped_column(
        index=True,
        nullable=True,
    )
    source_ref: Mapped[str | None] = mapped_column(
        String(120),
        index=True,
        nullable=True,
    )
    source_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )

    keywords: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    weight: Mapped[int] = mapped_column(
        default=1,
        nullable=False,
    )

    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
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
