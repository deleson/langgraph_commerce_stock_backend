from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DailyReportStatus(StrEnum):
    GENERATED = "generated"
    FALLBACK = "fallback"
    FAILED = "failed"


class DailyReportSource(StrEnum):
    MANUAL = "manual"
    API = "api"
    BACKGROUND_TASK = "background_task"
    SCHEDULER = "scheduler"


class DailyReportSectionType(StrEnum):
    OVERVIEW = "overview"
    MARKET_MOVEMENT = "market_movement"
    TECHNICAL_STATUS = "technical_status"
    STRATEGY_SIGNAL = "strategy_signal"
    CANDIDATE_PRIORITY = "candidate_priority"
    RISK_WARNING = "risk_warning"
    PERSONALIZED_NOTE = "personalized_note"


class DailyReportAIStatus(StrEnum):
    NOT_USED = "not_used"
    SUCCESS = "success"
    QUOTA_BLOCKED = "quota_blocked"
    LLM_ERROR = "llm_error"
    PARSE_ERROR = "parse_error"
    FALLBACK = "fallback"


class DailyReportUnavailableReason(StrEnum):
    EMPTY_WATCHLIST = "empty_watchlist"
    NO_DATA = "no_data"
    DATA_ERROR = "data_error"
    GENERATION_FAILED = "generation_failed"


class DailyReportGenerateRequest(BaseModel):
    report_date: date | None = Field(
        default=None,
        description="Report date. Defaults to today in service layer when omitted.",
    )
    use_ai: bool = Field(
        default=True,
        description="Whether to use AI to polish and explain the deterministic report.",
    )
    force_rebuild: bool = Field(
        default=False,
        description="Whether to rebuild the report when a report already exists for the date.",
    )
    notify: bool = Field(
        default=True,
        description="Whether to create a notification after report generation.",
    )
    include_candidates: bool = Field(
        default=True,
        description="Whether to include stock candidate scoring summary.",
    )
    include_user_profile: bool = Field(
        default=True,
        description="Whether to include user profile context.",
    )
    include_relevant_memories: bool = Field(
        default=True,
        description="Whether to include relevant memory context.",
    )
    max_watchlist_items: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum watchlist items to include in one report.",
    )
    max_candidate_items: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum candidate items to include in one report.",
    )


class DailyReportTaskPayload(DailyReportGenerateRequest):
    target_user_id: int | None = Field(
        default=None,
        description="Target user id for scheduler/background task. API layer should use current_user instead.",
    )


class DailyReportListQuery(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    status: DailyReportStatus | None = None
    source: DailyReportSource | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_date_range(self) -> "DailyReportListQuery":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be less than or equal to end_date")
        return self


class DailyReportSection(BaseModel):
    section_type: DailyReportSectionType
    title: str = Field(min_length=1, max_length=100)
    summary: str = Field(default="", max_length=2000)
    items: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DailyReportStockSnapshot(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    market: str = Field(min_length=1, max_length=16)
    name: str | None = Field(default=None, max_length=100)
    latest_price: Decimal | None = None
    change_percent: float | None = None
    volume_ratio: float | None = None
    data_quality_status: str | None = None
    strategy_signal: str | None = None
    strategy_strength: str | None = None
    candidate_score: int | None = Field(default=None, ge=0, le=100)
    candidate_grade: str | None = Field(default=None, max_length=8)


class DailyReportInputSnapshot(BaseModel):
    report_date: date
    source: DailyReportSource
    watchlist_count: int = Field(default=0, ge=0)
    included_stock_count: int = Field(default=0, ge=0)
    include_candidates: bool = True
    include_user_profile: bool = True
    include_relevant_memories: bool = True
    use_ai: bool = True
    notify: bool = True


class DailyReportCreate(BaseModel):
    user_id: int
    report_date: date
    status: DailyReportStatus
    source: DailyReportSource
    summary: str = Field(default="", max_length=4000)
    sections: list[DailyReportSection] = Field(default_factory=list)
    stock_snapshots: list[DailyReportStockSnapshot] = Field(default_factory=list)
    input_snapshot: DailyReportInputSnapshot
    market_snapshot: dict[str, Any] = Field(default_factory=dict)
    technical_snapshot: dict[str, Any] = Field(default_factory=dict)
    strategy_signal_snapshot: dict[str, Any] = Field(default_factory=dict)
    candidate_snapshot: dict[str, Any] = Field(default_factory=dict)
    profile_snapshot: dict[str, Any] = Field(default_factory=dict)
    memory_snapshot: dict[str, Any] = Field(default_factory=dict)
    ai_used: bool = False
    ai_status: DailyReportAIStatus = DailyReportAIStatus.NOT_USED
    ai_usage_log_id: int | None = None
    notification_id: int | None = None
    unavailable_reason: DailyReportUnavailableReason | None = None
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = Field(
        default="本每日简报仅基于历史行情、技术指标、策略信号和用户自选股生成，只作为研究参考，不构成投资建议。",
        max_length=500,
    )


class DailyReportUpdate(BaseModel):
    status: DailyReportStatus | None = None
    source: DailyReportSource | None = None
    summary: str | None = Field(default=None, max_length=4000)
    input_snapshot: DailyReportInputSnapshot | None = None
    sections: list[DailyReportSection] | None = None
    stock_snapshots: list[DailyReportStockSnapshot] | None = None
    market_snapshot: dict[str, Any] | None = None
    technical_snapshot: dict[str, Any] | None = None
    strategy_signal_snapshot: dict[str, Any] | None = None
    candidate_snapshot: dict[str, Any] | None = None
    profile_snapshot: dict[str, Any] | None = None
    memory_snapshot: dict[str, Any] | None = None
    ai_used: bool | None = None
    ai_status: DailyReportAIStatus | None = None
    ai_usage_log_id: int | None = None
    notification_id: int | None = None
    unavailable_reason: DailyReportUnavailableReason | None = None
    warnings: list[str] | None = None
    disclaimer: str | None = Field(default=None, max_length=500)


class DailyReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    report_date: date
    status: DailyReportStatus
    source: DailyReportSource
    summary: str
    sections: list[DailyReportSection] = Field(default_factory=list)
    stock_snapshots: list[DailyReportStockSnapshot] = Field(default_factory=list)
    input_snapshot: DailyReportInputSnapshot | None = None
    market_snapshot: dict[str, Any] = Field(default_factory=dict)
    technical_snapshot: dict[str, Any] = Field(default_factory=dict)
    strategy_signal_snapshot: dict[str, Any] = Field(default_factory=dict)
    candidate_snapshot: dict[str, Any] = Field(default_factory=dict)
    profile_snapshot: dict[str, Any] = Field(default_factory=dict)
    memory_snapshot: dict[str, Any] = Field(default_factory=dict)
    ai_used: bool = False
    ai_status: DailyReportAIStatus = DailyReportAIStatus.NOT_USED
    ai_usage_log_id: int | None = None
    notification_id: int | None = None
    unavailable_reason: DailyReportUnavailableReason | None = None
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str
    created_at: datetime
    updated_at: datetime


class DailyReportListResponse(BaseModel):
    total: int = Field(ge=0)
    items: list[DailyReportResponse]


class DailyReportTodayResponse(BaseModel):
    exists: bool
    report: DailyReportResponse | None = None
    message: str | None = None


class DailyReportGenerationResponse(BaseModel):
    report: DailyReportResponse
    created: bool = Field(
        description="Whether a new report was created. False means an existing report was reused.",
    )
    notification_created: bool = False
    ai_used: bool = False
    fallback_used: bool = False