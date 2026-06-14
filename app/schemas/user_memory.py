"""用户记忆与用户画像 Schema。

用户记忆用于沉淀用户风险偏好、关注市场、研究习惯和历史上下文。
所有记忆都必须按 user_id 隔离，不能跨用户泄露。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


UserMemoryStatus = Literal[
    "active",
    "inactive",
]

UserMemoryType = Literal[
    "risk_preference",
    "market_interest",
    "symbol_interest",
    "research_preference",
    "risk_focus",
    "communication_preference",
    "analysis_context_preference",
    "feature_usage",
]

UserMemorySourceType = Literal[
    "user_preference",
    "watchlist",
    "analysis_record",
    "conversation_message",
    "react_trace",
    "backtest_request",
    "stock_candidate_request",
    "manual",
    "system",
]

UserMemoryConfidence = Literal[
    "low",
    "medium",
    "high",
]

UserProfileStatus = Literal[
    "active",
    "stale",
    "inactive",
]


class UserMemorySourceSnapshot(BaseModel):
    """用户记忆来源快照。"""

    source_type: UserMemorySourceType
    source_id: int | None = Field(default=None, ge=1)
    source_ref: str | None = Field(default=None, max_length=120)
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class UserMemoryCreate(BaseModel):
    """创建用户记忆的数据结构。"""

    user_id: int = Field(gt=0)

    memory_type: UserMemoryType
    status: UserMemoryStatus = "active"
    confidence: UserMemoryConfidence = "medium"

    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=1000)
    summary: str | None = Field(default=None, max_length=500)

    source_type: UserMemorySourceType
    source_id: int | None = Field(default=None, ge=1)
    source_ref: str | None = Field(default=None, max_length=120)
    source_metadata: dict[str, Any] = Field(default_factory=dict)

    keywords: list[str] = Field(default_factory=list, max_length=20)
    weight: int = Field(default=1, ge=1, le=100)

    occurred_at: datetime | None = None
    expires_at: datetime | None = None

    @field_validator("title", "content", "summary", "source_ref", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("keywords", mode="before")
    @classmethod
    def normalize_keywords(cls, value: list[str] | None) -> list[str]:
        if value is None:
            return []

        normalized_keywords: list[str] = []
        seen: set[str] = set()

        for item in value:
            keyword = str(item).strip()
            if not keyword:
                continue

            lowered = keyword.lower()
            if lowered in seen:
                continue

            seen.add(lowered)
            normalized_keywords.append(keyword[:50])

        return normalized_keywords[:20]


class UserMemoryUpdate(BaseModel):
    """更新用户记忆的数据结构。"""

    status: UserMemoryStatus | None = None
    confidence: UserMemoryConfidence | None = None

    title: str | None = Field(default=None, min_length=1, max_length=120)
    content: str | None = Field(default=None, min_length=1, max_length=1000)
    summary: str | None = Field(default=None, max_length=500)

    keywords: list[str] | None = Field(default=None, max_length=20)
    weight: int | None = Field(default=None, ge=1, le=100)
    expires_at: datetime | None = None

    @field_validator("title", "content", "summary", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("keywords", mode="before")
    @classmethod
    def normalize_keywords(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None

        normalized_keywords: list[str] = []
        seen: set[str] = set()

        for item in value:
            keyword = str(item).strip()
            if not keyword:
                continue

            lowered = keyword.lower()
            if lowered in seen:
                continue

            seen.add(lowered)
            normalized_keywords.append(keyword[:50])

        return normalized_keywords[:20]


class UserMemoryResponse(BaseModel):
    """用户记忆响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int

    memory_type: str
    status: str
    confidence: str

    title: str
    content: str
    summary: str | None

    source_type: str
    source_id: int | None
    source_ref: str | None
    source_metadata: dict[str, Any]

    keywords: list[str]
    weight: int

    occurred_at: datetime | None
    expires_at: datetime | None

    created_at: datetime
    updated_at: datetime


class UserMemoryListQuery(BaseModel):
    """用户记忆列表查询条件。"""

    memory_type: UserMemoryType | None = None
    status: UserMemoryStatus | None = None
    confidence: UserMemoryConfidence | None = None
    source_type: UserMemorySourceType | None = None

    keyword: str | None = Field(default=None, min_length=1, max_length=50)
    include_inactive: bool = False

    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator("keyword", mode="before")
    @classmethod
    def normalize_keyword(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value


class UserMemoryListResponse(BaseModel):
    """用户记忆列表响应。"""

    items: list[UserMemoryResponse]
    total: int
    limit: int
    offset: int


class UserProfileSummary(BaseModel):
    """用户画像摘要。"""

    risk_preference: str | None = None
    preferred_markets: list[str] = Field(default_factory=list)
    frequent_symbols: list[str] = Field(default_factory=list)
    interest_tags: list[str] = Field(default_factory=list)
    research_preferences: list[str] = Field(default_factory=list)
    risk_focuses: list[str] = Field(default_factory=list)
    communication_preferences: list[str] = Field(default_factory=list)

    summary: str | None = Field(default=None, max_length=1000)
    evidence_count: int = Field(default=0, ge=0)
    profile_metadata: dict[str, Any] = Field(default_factory=dict)


class UserProfileCreate(BaseModel):
    """创建用户画像的数据结构。"""

    user_id: int = Field(gt=0)

    status: UserProfileStatus = "active"
    profile_version: int = Field(default=1, ge=1)

    summary: UserProfileSummary = Field(default_factory=UserProfileSummary)

    generated_from_memory_count: int = Field(default=0, ge=0)
    generated_from_message_count: int = Field(default=0, ge=0)
    generated_from_analysis_count: int = Field(default=0, ge=0)

    refreshed_at: datetime | None = None


class UserProfileUpdate(BaseModel):
    """更新用户画像的数据结构。"""

    status: UserProfileStatus | None = None
    profile_version: int | None = Field(default=None, ge=1)

    summary: UserProfileSummary | None = None

    generated_from_memory_count: int | None = Field(default=None, ge=0)
    generated_from_message_count: int | None = Field(default=None, ge=0)
    generated_from_analysis_count: int | None = Field(default=None, ge=0)

    refreshed_at: datetime | None = None


class UserProfileResponse(BaseModel):
    """用户画像响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int

    status: str
    profile_version: int

    summary: UserProfileSummary

    generated_from_memory_count: int
    generated_from_message_count: int
    generated_from_analysis_count: int

    refreshed_at: datetime | None

    created_at: datetime
    updated_at: datetime


class UserProfileRefreshRequest(BaseModel):
    """刷新用户画像请求体。"""

    include_inactive_memories: bool = False
    force_refresh: bool = False
    reason: str | None = Field(default=None, max_length=200)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value


class UserProfileRefreshResponse(BaseModel):
    """刷新用户画像响应体。"""

    status: UserProfileStatus
    profile: UserProfileResponse | None = None
    refreshed: bool
    memory_count: int = 0
    message: str
