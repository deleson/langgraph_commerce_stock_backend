"""分析会话消息 Model。

analysis_conversation_messages 表保存普通追问、ReAct 追问、工具 Observation
和系统摘要消息，使 AI 会话可以被回放和审计。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AnalysisConversationMessage(Base):
    """分析会话消息表。"""

    __tablename__ = "analysis_conversation_messages"

    __table_args__ = (
        CheckConstraint(
            "role IN ('user','assistant','tool','system')",
            name="analysis_conversation_message_role_valid",
        ),
        CheckConstraint(
            "message_type IN ('normal_follow_up','react_follow_up','tool_observation','system_summary','error')",
            name="analysis_conversation_message_type_valid",
        ),
        CheckConstraint(
            "source IN ('normal_follow_up','react_follow_up','system')",
            name="analysis_conversation_message_source_valid",
        ),
        CheckConstraint(
            "sequence_no >= 1",
            name="analysis_conversation_message_sequence_no_positive",
        ),
        UniqueConstraint(
            "user_id",
            "analysis_thread_id",
            "sequence_no",
            name="uq_analysis_conversation_messages_user_thread_sequence",
        ),
        # 按用户、线程和序号读取，是恢复会话上下文的主要查询路径。
        Index(
            "ix_analysis_conversation_messages_user_thread_sequence",
            "user_id",
            "analysis_thread_id",
            "sequence_no",
        ),
        Index(
            "ix_analysis_conversation_messages_thread_created_at",
            "analysis_thread_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # 会话消息必须归属于当前用户，避免跨用户读取分析上下文。
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

    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    message_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )
    content: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    source: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )
    sequence_no: Mapped[int] = mapped_column(
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
