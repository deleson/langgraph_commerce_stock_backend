"""用户记忆向量 Model。

user_memory_embeddings 表保存用户记忆文本对应的向量，
用于相似记忆检索和 AI 上下文增强，不用于跨用户共享。
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


class UserMemoryEmbedding(Base):
    """用户记忆向量表。"""

    __tablename__ = "user_memory_embeddings"

    __table_args__ = (
        CheckConstraint(
            "status IN ('active','stale','failed','inactive')",
            name="user_memory_embedding_status_valid",
        ),
        CheckConstraint(
            "embedding_provider IN ('openai_compatible','deepseek','local','mock')",
            name="user_memory_embedding_provider_valid",
        ),
        CheckConstraint(
            "build_source IN ("
            "'memory_create',"
            "'memory_update',"
            "'manual_rebuild',"
            "'background_rebuild',"
            "'system'"
            ")",
            name="user_memory_embedding_build_source_valid",
        ),
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
            name="user_memory_embedding_memory_type_valid",
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
            name="user_memory_embedding_source_type_valid",
        ),
        CheckConstraint(
            "embedding_dimension > 0 AND embedding_dimension <= 8192",
            name="user_memory_embedding_dimension_range",
        ),
        UniqueConstraint(
            "memory_id",
            "embedding_provider",
            "embedding_model",
            "content_hash",
            name="uq_user_memory_embeddings_memory_model_hash",
        ),
        # 记忆文本内容未变化时，同一模型下不重复生成向量。
        Index(
            "ix_user_memory_embeddings_user_status_created_at",
            "user_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_user_memory_embeddings_user_type_status",
            "user_id",
            "memory_type",
            "status",
        ),
        Index(
            "ix_user_memory_embeddings_memory_status",
            "memory_id",
            "status",
        ),
        Index(
            "ix_user_memory_embeddings_user_content_hash",
            "user_id",
            "content_hash",
        ),
        Index(
            "ix_user_memory_embeddings_provider_model",
            "embedding_provider",
            "embedding_model",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # user_id 用于向量检索隔离，防止检索到其他用户的记忆。
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    memory_id: Mapped[int] = mapped_column(
        ForeignKey("user_memories.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="active",
        index=True,
        nullable=False,
    )

    embedding_provider: Mapped[str] = mapped_column(
        String(60),
        default="mock",
        index=True,
        nullable=False,
    )
    embedding_model: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )
    embedding_dimension: Mapped[int] = mapped_column(
        nullable=False,
    )
    embedding_vector: Mapped[list[float]] = mapped_column(
        JSON,
        nullable=False,
    )

    embedding_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    content_hash: Mapped[str] = mapped_column(
        String(128),
        index=True,
        nullable=False,
    )

    build_source: Mapped[str] = mapped_column(
        String(40),
        default="system",
        nullable=False,
    )

    memory_type: Mapped[str] = mapped_column(
        String(60),
        index=True,
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(
        String(60),
        index=True,
        nullable=False,
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

    last_embedded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
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
