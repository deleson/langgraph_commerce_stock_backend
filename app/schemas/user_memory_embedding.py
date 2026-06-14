"""用户记忆向量与检索 Schema。

记忆向量用于把用户历史上下文转成可检索结构，供 AI 分析和 ReAct 追问补充背景。
检索结果只用于上下文增强，不构成投资建议。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.user_memory import (
    UserMemoryConfidence,
    UserMemorySourceType,
    UserMemoryType,
)


UserMemoryEmbeddingStatus = Literal[
    "active",
    "stale",
    "failed",
    "inactive",
]

UserMemoryEmbeddingProvider = Literal[
    "openai_compatible",
    "deepseek",
    "local",
    "mock",
]

UserMemoryEmbeddingBuildSource = Literal[
    "memory_create",
    "memory_update",
    "manual_rebuild",
    "background_rebuild",
    "system",
]

UserMemoryRetrievalStatus = Literal[
    "available",
    "unavailable",
]

UserMemoryRetrievalUnavailableReason = Literal[
    "empty_query",
    "no_embeddings",
    "embedding_unavailable",
    "retrieval_error",
]


class UserMemoryEmbeddingCreate(BaseModel):
    """创建用户记忆向量的数据结构。"""

    user_id: int = Field(gt=0)
    memory_id: int = Field(gt=0)

    status: UserMemoryEmbeddingStatus = "active"

    embedding_provider: UserMemoryEmbeddingProvider = "mock"
    embedding_model: str = Field(min_length=1, max_length=100)
    embedding_dimension: int = Field(gt=0, le=8192)
    embedding_vector: list[float] = Field(min_length=1, max_length=8192)

    embedding_text: str = Field(min_length=1, max_length=2000)
    content_hash: str = Field(min_length=1, max_length=128)

    build_source: UserMemoryEmbeddingBuildSource = "system"

    memory_type: UserMemoryType
    source_type: UserMemorySourceType
    source_ref: str | None = Field(default=None, max_length=120)
    source_metadata: dict[str, Any] = Field(default_factory=dict)

    last_embedded_at: datetime | None = None
    error_message: str | None = Field(default=None, max_length=1000)

    @field_validator("embedding_model", "embedding_text", "content_hash", "source_ref", "error_message", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @model_validator(mode="after")
    def validate_embedding_dimension(self) -> "UserMemoryEmbeddingCreate":
        if len(self.embedding_vector) != self.embedding_dimension:
            raise ValueError("embedding_dimension must match embedding_vector length")
        return self


class UserMemoryEmbeddingUpdate(BaseModel):
    """更新用户记忆向量的数据结构。"""

    status: UserMemoryEmbeddingStatus | None = None

    embedding_provider: UserMemoryEmbeddingProvider | None = None
    embedding_model: str | None = Field(default=None, min_length=1, max_length=100)
    embedding_dimension: int | None = Field(default=None, gt=0, le=8192)
    embedding_vector: list[float] | None = Field(default=None, min_length=1, max_length=8192)

    embedding_text: str | None = Field(default=None, min_length=1, max_length=2000)
    content_hash: str | None = Field(default=None, min_length=1, max_length=128)

    build_source: UserMemoryEmbeddingBuildSource | None = None

    source_metadata: dict[str, Any] | None = None
    last_embedded_at: datetime | None = None
    error_message: str | None = Field(default=None, max_length=1000)

    @field_validator("embedding_model", "embedding_text", "content_hash", "error_message", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @model_validator(mode="after")
    def validate_embedding_dimension(self) -> "UserMemoryEmbeddingUpdate":
        if self.embedding_vector is not None and self.embedding_dimension is not None:
            if len(self.embedding_vector) != self.embedding_dimension:
                raise ValueError("embedding_dimension must match embedding_vector length")
        return self


class UserMemoryEmbeddingResponse(BaseModel):
    """用户记忆向量响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    memory_id: int

    status: str

    embedding_provider: str
    embedding_model: str
    embedding_dimension: int

    embedding_text: str
    content_hash: str

    build_source: str

    memory_type: str
    source_type: str
    source_ref: str | None
    source_metadata: dict[str, Any]

    last_embedded_at: datetime | None
    error_message: str | None

    created_at: datetime
    updated_at: datetime


class UserMemoryEmbeddingListQuery(BaseModel):
    """用户记忆向量列表查询条件。"""

    status: UserMemoryEmbeddingStatus | None = None
    memory_type: UserMemoryType | None = None
    source_type: UserMemorySourceType | None = None
    embedding_provider: UserMemoryEmbeddingProvider | None = None

    include_inactive: bool = False

    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class UserMemoryEmbeddingListResponse(BaseModel):
    """用户记忆向量列表响应。"""

    items: list[UserMemoryEmbeddingResponse]
    total: int
    limit: int
    offset: int


class UserMemoryRetrievalRequest(BaseModel):
    """用户记忆相似检索请求体。"""

    query: str = Field(min_length=1, max_length=1000)

    top_k: int = Field(default=5, ge=1, le=10)
    min_similarity_score: float | None = Field(default=None, ge=0, le=1)

    memory_types: list[UserMemoryType] = Field(default_factory=list, max_length=20)
    include_inactive: bool = False
    include_content: bool = False

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise ValueError("query 不能为空")
            return normalized
        return value

    @field_validator("memory_types", mode="before")
    @classmethod
    def normalize_memory_types(cls, value: list[str] | None) -> list[str]:
        if value is None:
            return []

        normalized_values: list[str] = []
        seen: set[str] = set()

        for item in value:
            memory_type = str(item).strip()
            if not memory_type:
                continue

            if memory_type in seen:
                continue

            seen.add(memory_type)
            normalized_values.append(memory_type)

        return normalized_values[:20]


class UserMemoryRetrievalItem(BaseModel):
    """用户记忆检索命中的单条结果。"""

    memory_id: int
    memory_type: UserMemoryType
    confidence: UserMemoryConfidence

    title: str
    summary: str | None = None
    content_excerpt: str | None = None
    keywords: list[str] = Field(default_factory=list)

    source_type: UserMemorySourceType
    source_ref: str | None = None

    similarity_score: float = Field(ge=0, le=1)
    embedding_id: int | None = None
    embedding_model: str | None = None

    occurred_at: datetime | None = None
    expires_at: datetime | None = None


class UserMemoryRetrievalInputSnapshot(BaseModel):
    """用户记忆检索输入快照。"""

    query: str
    top_k: int
    min_similarity_score: float | None = None
    memory_types: list[UserMemoryType] = Field(default_factory=list)
    include_inactive: bool = False
    include_content: bool = False
    embedding_provider: UserMemoryEmbeddingProvider | None = None
    embedding_model: str | None = None


class UserMemoryRetrievalResponse(BaseModel):
    """用户记忆检索响应体。"""

    status: UserMemoryRetrievalStatus
    unavailable_reason: UserMemoryRetrievalUnavailableReason | None = None

    summary: str
    items: list[UserMemoryRetrievalItem] = Field(default_factory=list)

    input_snapshot: UserMemoryRetrievalInputSnapshot

    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = "相似记忆检索仅用于补充用户历史上下文，不构成投资建议。"


class UserMemoryEmbeddingRebuildRequest(BaseModel):
    """重建用户记忆向量请求体。"""

    memory_ids: list[int] = Field(default_factory=list, max_length=100)
    force_rebuild: bool = False
    only_failed: bool = False
    only_stale: bool = False
    reason: str | None = Field(default=None, max_length=200)

    @field_validator("memory_ids", mode="before")
    @classmethod
    def normalize_memory_ids(cls, value: list[int] | None) -> list[int]:
        if value is None:
            return []

        normalized_ids: list[int] = []
        seen: set[int] = set()

        for item in value:
            memory_id = int(item)
            if memory_id <= 0:
                continue

            if memory_id in seen:
                continue

            seen.add(memory_id)
            normalized_ids.append(memory_id)

        return normalized_ids[:100]

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value


class UserMemoryEmbeddingStatsResponse(BaseModel):
    """用户记忆向量统计响应体。"""

    user_id: int

    total_memories: int = Field(ge=0)
    total_embeddings: int = Field(ge=0)
    active_embeddings: int = Field(ge=0)
    stale_embeddings: int = Field(ge=0)
    failed_embeddings: int = Field(ge=0)
    inactive_embeddings: int = Field(ge=0)

    embedding_provider: str | None = None
    embedding_model: str | None = None
    last_embedded_at: datetime | None = None
