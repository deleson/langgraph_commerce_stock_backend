"""后台任务 Schema。

本文件定义后台任务提交、payload、状态和查询响应。
API 只负责创建和查询任务，真正执行由 Celery Worker 分发到具体处理器。
"""

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
from app.schemas.user_memory import UserProfileRefreshRequest
from app.schemas.user_memory_embedding import UserMemoryEmbeddingRebuildRequest
from app.schemas.quant_alert import QuantAlertScanRequest
from app.schemas.paper_trading import PaperTradingTickRequest

BackgroundTaskType = Literal[
    "market_data_sync",
    "watchlist_candle_sync",
    "stock_analysis_async",
    "candidate_scoring_async",
    "candidate_ai_explanation_async",
    "user_profile_refresh",
    "user_memory_embedding_rebuild",
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
    """行情同步后台任务 payload。"""

    symbol: str = Field(..., min_length=1, max_length=32)
    market: MarketCode = "US"
    timeframe: CandleTimeframe = "1d"
    limit: int | None = Field(default=None, ge=1, le=1000)
    adjust_type: AdjustType = "none"
    source: MarketDataSource = "mock"
    start_date: str | None = Field(default=None, max_length=32)
    end_date: str | None = Field(default=None, max_length=32)
    force_refresh: bool = False

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

class WatchlistCandleSyncTaskPayload(BaseModel):
    """批量同步自选股 K 线后台任务 payload。"""

    market: MarketCode = "CN"
    timeframe: CandleTimeframe = "1d"
    limit: int = Field(default=120, ge=1, le=1000)
    adjust_type: AdjustType = "none"
    source: MarketDataSource = "baostock"
    fallback_sources: list[MarketDataSource] = Field(default_factory=lambda: ["tushare"])
    max_symbols: int = Field(default=300, ge=1, le=5000)
    batch_size: int = Field(default=50, ge=1, le=500)
    stale_after_days: int = Field(default=3, ge=0, le=365)

    @field_validator("fallback_sources", mode="before")
    @classmethod
    def normalize_fallback_sources(
        cls,
        value: list[str] | str | None,
    ) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        return [str(item).strip().lower() for item in value if str(item).strip()]


class StockAnalysisAsyncTaskPayload(BaseModel):
    """异步个股分析后台任务 payload。"""

    symbol: str = Field(..., min_length=1, max_length=20)
    market: MarketCode = "US"
    analysis_type: Literal["stock_basic"] = "stock_basic"
    thread_id: str | None = Field(default=None, min_length=1, max_length=100)
    notify_when_done: bool = True

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("thread_id", mode="before")
    @classmethod
    def normalize_thread_id(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

class UserProfileRefreshTaskPayload(UserProfileRefreshRequest):
    """刷新当前用户画像的后台任务 payload。"""

    pass

class UserMemoryEmbeddingRebuildTaskPayload(UserMemoryEmbeddingRebuildRequest):
    """重建当前用户记忆向量的后台任务 payload。"""

    pass

class QuantAlertScanTaskPayload(QuantAlertScanRequest):
    """执行当前用户量化提醒扫描的后台任务 payload。"""

    pass

class PaperTradingTickTaskPayload(PaperTradingTickRequest):
    """执行当前用户纸面交易 tick 的后台任务 payload。"""

    pass

class BackgroundTaskCreateRequest(BaseModel):
    """提交后台任务请求体。"""

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
    """后台任务提交成功后的响应体。"""

    task_id: int
    task_type: BackgroundTaskType
    status: BackgroundTaskStatus
    celery_task_id: str | None = None
    message: str


class BackgroundTaskResponse(BaseModel):
    """后台任务详情响应体。"""

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
    """后台任务列表查询条件。"""

    task_type: BackgroundTaskType | None = None
    status: BackgroundTaskStatus | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class BackgroundTaskListResponse(BaseModel):
    """后台任务列表响应。"""

    items: list[BackgroundTaskResponse]
    total: int
    limit: int
    offset: int
