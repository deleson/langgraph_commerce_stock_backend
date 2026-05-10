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
    status: MarketDataSyncStatusValue | None = None
    last_success_at: datetime | None = None
    last_failed_at: datetime | None = None
    earliest_candle_time: datetime | None = None
    latest_candle_time: datetime | None = None
    candle_count: int | None = Field(default=None, ge=0)
    last_error_message: str | None = Field(default=None, max_length=500)


class MarketDataSyncStatusResponse(BaseModel):
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
    status: MarketDataSyncLogStatus | None = None
    fetched_count: int | None = Field(default=None, ge=0)
    normalized_count: int | None = Field(default=None, ge=0)
    saved_count: int | None = Field(default=None, ge=0)
    error_message: str | None = Field(default=None, max_length=500)
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class MarketDataSyncLogResponse(BaseModel):
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