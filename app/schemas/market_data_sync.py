"""行情同步、同步日志与数据质量报告 Schema。

本文件用于记录行情同步状态、单次同步日志，以及后续量化链路依赖的数据质量报告。
数据质量报告会影响策略信号、AI 分析、回测和纸面交易是否继续执行。
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.market_data import (
    AdjustType,
    CandleTimeframe,
    MarketCode,
    MarketDataSource,
)


MarketDataSyncStatusValue = Literal[
    "never_synced",
    "success",
    "partial",
    "failed",
]
MarketDataSyncLogStatus = Literal[
    "running",
    "success",
    "partial",
    "failed",
]


class MarketDataSyncStatusCreate(BaseModel):
    """创建或初始化某只股票同步状态的数据结构。"""

    symbol_id: int | None = None
    symbol: str = Field(min_length=1, max_length=20)
    market: MarketCode
    timeframe: CandleTimeframe = "1d"
    source: MarketDataSource
    adjust_type: AdjustType = "none"
    status: MarketDataSyncStatusValue = "never_synced"
    last_success_at: datetime | None = None
    last_failed_at: datetime | None = None
    earliest_candle_time: datetime | None = None
    latest_candle_time: datetime | None = None
    candle_count: int = Field(default=0, ge=0)
    last_error_message: str | None = Field(default=None, max_length=500)

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class MarketDataSyncStatusUpdate(BaseModel):
    """更新行情同步状态的数据结构。"""

    status: MarketDataSyncStatusValue | None = None
    last_success_at: datetime | None = None
    last_failed_at: datetime | None = None
    earliest_candle_time: datetime | None = None
    latest_candle_time: datetime | None = None
    candle_count: int | None = Field(default=None, ge=0)
    last_error_message: str | None = Field(default=None, max_length=500)


class MarketDataSyncStatusResponse(BaseModel):
    """行情同步状态响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol_id: int | None
    symbol: str
    market: str
    timeframe: str
    source: str
    adjust_type: str
    status: str
    last_success_at: datetime | None
    last_failed_at: datetime | None
    earliest_candle_time: datetime | None
    latest_candle_time: datetime | None
    candle_count: int
    last_error_message: str | None
    created_at: datetime
    updated_at: datetime


class MarketDataSyncLogCreate(BaseModel):
    """创建单次行情同步日志的数据结构。"""

    symbol_id: int | None = None
    symbol: str = Field(min_length=1, max_length=20)
    market: MarketCode
    timeframe: CandleTimeframe = "1d"
    source: MarketDataSource
    adjust_type: AdjustType = "none"
    status: MarketDataSyncLogStatus = "running"
    fetched_count: int = Field(default=0, ge=0)
    normalized_count: int = Field(default=0, ge=0)
    saved_count: int = Field(default=0, ge=0)
    error_message: str | None = Field(default=None, max_length=500)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class MarketDataSyncLogUpdate(BaseModel):
    """更新单次行情同步日志的数据结构。"""

    status: MarketDataSyncLogStatus | None = None
    fetched_count: int | None = Field(default=None, ge=0)
    normalized_count: int | None = Field(default=None, ge=0)
    saved_count: int | None = Field(default=None, ge=0)
    error_message: str | None = Field(default=None, max_length=500)
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class MarketDataSyncLogResponse(BaseModel):
    """行情同步日志响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol_id: int | None
    symbol: str
    market: str
    timeframe: str
    source: str
    adjust_type: str
    status: str
    fetched_count: int
    normalized_count: int
    saved_count: int
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    created_at: datetime


class MarketDataSyncStatusQuery(BaseModel):
    """查询行情同步状态列表的过滤条件。"""

    symbol: str | None = Field(default=None, min_length=1, max_length=20)
    market: MarketCode | None = None
    timeframe: CandleTimeframe | None = None
    source: MarketDataSource | None = None
    adjust_type: AdjustType | None = None
    status: MarketDataSyncStatusValue | None = None
    limit: int = Field(default=50, ge=1, le=200)

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class MarketDataSyncLogQuery(BaseModel):
    """查询行情同步日志列表的过滤条件。"""

    symbol: str | None = Field(default=None, min_length=1, max_length=20)
    market: MarketCode | None = None
    timeframe: CandleTimeframe | None = None
    source: MarketDataSource | None = None
    adjust_type: AdjustType | None = None
    status: MarketDataSyncLogStatus | None = None
    limit: int = Field(default=50, ge=1, le=200)

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class MarketDataQualityReport(BaseModel):
    """数据质量报告。

    is_empty、is_enough、is_stale 会作为量化和 AI 链路的门控依据，
    避免在无数据、数据不足或数据过旧时继续生成看似确定的结论。
    """

    symbol: str = Field(min_length=1, max_length=20)
    market: MarketCode
    timeframe: CandleTimeframe
    source: MarketDataSource | str | None = None
    adjust_type: AdjustType = "none"
    candle_count: int = Field(ge=0)
    duplicate_count: int = Field(default=0, ge=0)
    earliest_candle_time: datetime | None = None
    latest_candle_time: datetime | None = None
    is_empty: bool = False
    is_enough: bool = True
    is_stale: bool = False
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value
