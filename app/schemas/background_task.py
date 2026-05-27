from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.market_data import (
    AdjustType,
    CandleTimeframe,
    MarketCode,
    MarketDataSource,
)


BackgroundTaskType = Literal[
    "market_data_sync",
    "stock_analysis_async",
    "candidate_scoring_async",
    "candidate_ai_explanation_async",
    "daily_report",
    "alert_scan",
    "paper_trading_tick",
]

BackgroundTaskStatus = Literal[
    "pending",
    "queued",
    "running",
    "success",
    "failed",
    "retrying",
    "cancelled",
]

BackgroundTaskPriority = Literal[
    "low",
    "normal",
    "high",
]

BackgroundTaskSource = Literal[
    "api",
    "system",
    "scheduler",
]


class MarketDataSyncTaskPayload(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=32)
    market: MarketCode = "US"
    timeframe: CandleTimeframe = "1d"
    adjust_type: AdjustType = "none"
    source: MarketDataSource = "mock"
    start_date: str | None = Field(default=None, max_length=32)
    end_date: str | None = Field(default=None, max_length=32)
    force_refresh: bool = False

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class BackgroundTaskCreateRequest(BaseModel):
    task_type: BackgroundTaskType
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: BackgroundTaskPriority = "normal"
    source: BackgroundTaskSource = "api"
    scheduled_for: datetime | None = None
    max_retries: int = Field(default=3, ge=0, le=5)

    @field_validator("payload")
    @classmethod
    def validate_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("payload 必须是对象结构")
        return value


class BackgroundTaskSubmitResponse(BaseModel):
    task_id: int
    task_type: BackgroundTaskType
    status: BackgroundTaskStatus
    celery_task_id: str | None = None
    message: str


class BackgroundTaskResponse(BaseModel):
    id: int
    user_id: int | None = None
    task_type: BackgroundTaskType
    status: BackgroundTaskStatus
    priority: BackgroundTaskPriority
    source: BackgroundTaskSource
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error_message: str | None = None
    celery_task_id: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    scheduled_for: datetime | None = None
    queued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class BackgroundTaskListQuery(BaseModel):
    task_type: BackgroundTaskType | None = None
    status: BackgroundTaskStatus | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class BackgroundTaskListResponse(BaseModel):
    items: list[BackgroundTaskResponse]
    total: int
    limit: int
    offset: int