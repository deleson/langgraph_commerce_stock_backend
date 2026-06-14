"""量化提醒 Schema。

量化提醒基于历史行情、数据质量、技术指标和策略信号规则触发。
提醒只作为研究线索，不构成投资建议，也不会执行真实交易。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.market_data import MarketCode


class QuantAlertRuleStatus(StrEnum):
    """量化提醒规则状态。"""

    ACTIVE = "active"
    INACTIVE = "inactive"


class QuantAlertRuleType(StrEnum):
    """量化提醒规则类型。"""

    STRATEGY_SIGNAL = "strategy_signal"
    STRONG_STRATEGY_SIGNAL = "strong_strategy_signal"
    STRATEGY_SCORE_THRESHOLD = "strategy_score_threshold"
    PRICE_CHANGE = "price_change"
    VOLUME_SPIKE = "volume_spike"
    DATA_QUALITY = "data_quality"


class QuantAlertTriggerDirection(StrEnum):
    """阈值类提醒的触发方向。"""

    ABOVE = "above"
    BELOW = "below"
    EQUAL = "equal"
    CHANGED = "changed"


class QuantAlertSeverity(StrEnum):
    """量化提醒严重程度。"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class QuantAlertEventStatus(StrEnum):
    """量化提醒事件处理状态。"""

    TRIGGERED = "triggered"
    ACKNOWLEDGED = "acknowledged"
    IGNORED = "ignored"


class QuantAlertScanStatus(StrEnum):
    """量化提醒扫描结果状态。"""

    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class QuantAlertScanSource(StrEnum):
    """量化提醒扫描触发来源。"""

    MANUAL = "manual"
    API = "api"
    BACKGROUND_TASK = "background_task"
    SCHEDULER = "scheduler"


class QuantAlertUnavailableReason(StrEnum):
    """量化提醒扫描不可用原因。"""

    EMPTY_WATCHLIST = "empty_watchlist"
    NO_ACTIVE_RULES = "no_active_rules"
    NO_DATA = "no_data"
    DATA_ERROR = "data_error"
    SCAN_FAILED = "scan_failed"


class QuantAlertRuleCreate(BaseModel):
    """创建量化提醒规则请求体。"""

    name: str = Field(min_length=1, max_length=120)
    rule_type: QuantAlertRuleType
    market: MarketCode | None = None
    symbol: str | None = Field(default=None, min_length=1, max_length=32)
    severity: QuantAlertSeverity = QuantAlertSeverity.WARNING
    trigger_direction: QuantAlertTriggerDirection | None = None
    threshold_value: Decimal | None = None
    cooldown_minutes: int = Field(default=1440, ge=0, le=60 * 24 * 30)
    enabled_notification: bool = True
    description: str | None = Field(default=None, max_length=500)
    rule_config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            normalized = value.strip().upper()
            return normalized or None
        return value

    @model_validator(mode="after")
    def validate_rule_threshold(self) -> "QuantAlertRuleCreate":
        if self.rule_type in {
            QuantAlertRuleType.STRATEGY_SCORE_THRESHOLD,
            QuantAlertRuleType.PRICE_CHANGE,
            QuantAlertRuleType.VOLUME_SPIKE,
        }:
            if self.threshold_value is None:
                raise ValueError("threshold_value is required for threshold alert rules")
            if self.trigger_direction is None:
                raise ValueError("trigger_direction is required for threshold alert rules")

        return self


class QuantAlertRuleUpdate(BaseModel):
    """更新量化提醒规则请求体。"""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    status: QuantAlertRuleStatus | None = None
    severity: QuantAlertSeverity | None = None
    trigger_direction: QuantAlertTriggerDirection | None = None
    threshold_value: Decimal | None = None
    cooldown_minutes: int | None = Field(default=None, ge=0, le=60 * 24 * 30)
    enabled_notification: bool | None = None
    description: str | None = Field(default=None, max_length=500)
    rule_config: dict[str, Any] | None = None


class QuantAlertRuleResponse(BaseModel):
    """量化提醒规则响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    rule_type: QuantAlertRuleType
    status: QuantAlertRuleStatus
    market: str | None = None
    symbol: str | None = None
    severity: QuantAlertSeverity
    trigger_direction: QuantAlertTriggerDirection | None = None
    threshold_value: Decimal | None = None
    cooldown_minutes: int
    enabled_notification: bool
    description: str | None = None
    rule_config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class QuantAlertRuleListQuery(BaseModel):
    """量化提醒规则列表查询条件。"""

    rule_type: QuantAlertRuleType | None = None
    status: QuantAlertRuleStatus | None = None
    market: MarketCode | None = None
    symbol: str | None = Field(default=None, min_length=1, max_length=32)
    include_inactive: bool = False
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            normalized = value.strip().upper()
            return normalized or None
        return value


class QuantAlertRuleListResponse(BaseModel):
    """量化提醒规则列表响应。"""

    total: int = Field(ge=0)
    items: list[QuantAlertRuleResponse]


class QuantAlertTriggerSnapshot(BaseModel):
    """量化提醒触发时的输入和结果快照。"""

    rule_type: QuantAlertRuleType
    symbol: str
    market: str
    trigger_value: Decimal | float | int | str | None = None
    threshold_value: Decimal | float | int | str | None = None
    trigger_direction: QuantAlertTriggerDirection | None = None
    strategy_signal: str | None = None
    strategy_strength: str | None = None
    strategy_score: int | None = Field(default=None, ge=0, le=100)
    price_change_percent: float | None = None
    volume_ratio: float | None = None
    data_quality_status: str | None = None
    data_quality_reason: str | None = None
    source_payload: dict[str, Any] = Field(default_factory=dict)


class QuantAlertEventCreate(BaseModel):
    """创建量化提醒事件的数据结构。"""

    user_id: int
    rule_id: int | None = None
    rule_type: QuantAlertRuleType
    symbol: str = Field(min_length=1, max_length=32)
    market: MarketCode
    title: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=1000)
    severity: QuantAlertSeverity
    status: QuantAlertEventStatus = QuantAlertEventStatus.TRIGGERED
    event_date: date
    triggered_at: datetime
    dedup_key: str = Field(min_length=1, max_length=255)
    trigger_snapshot: QuantAlertTriggerSnapshot
    notification_id: int | None = None

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class QuantAlertEventUpdate(BaseModel):
    """更新量化提醒事件状态的数据结构。"""

    status: QuantAlertEventStatus | None = None
    notification_id: int | None = None


class QuantAlertEventResponse(BaseModel):
    """量化提醒事件响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    rule_id: int | None = None
    rule_type: QuantAlertRuleType
    symbol: str
    market: str
    title: str
    message: str
    severity: QuantAlertSeverity
    status: QuantAlertEventStatus
    event_date: date
    triggered_at: datetime
    dedup_key: str
    trigger_snapshot: QuantAlertTriggerSnapshot | None = None
    notification_id: int | None = None
    created_at: datetime
    updated_at: datetime


class QuantAlertEventListQuery(BaseModel):
    """量化提醒事件列表查询条件。"""

    rule_type: QuantAlertRuleType | None = None
    status: QuantAlertEventStatus | None = None
    severity: QuantAlertSeverity | None = None
    market: MarketCode | None = None
    symbol: str | None = Field(default=None, min_length=1, max_length=32)
    start_date: date | None = None
    end_date: date | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            normalized = value.strip().upper()
            return normalized or None
        return value

    @model_validator(mode="after")
    def validate_date_range(self) -> "QuantAlertEventListQuery":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be less than or equal to end_date")
        return self


class QuantAlertEventListResponse(BaseModel):
    """量化提醒事件列表响应。"""

    total: int = Field(ge=0)
    items: list[QuantAlertEventResponse]


class QuantAlertScanRequest(BaseModel):
    """执行量化提醒扫描请求体。

    target_user_id 仅供调度器和后台任务使用，API 层会强制使用当前登录用户。
    """

    target_user_id: int | None = Field(
        default=None,
        description="Only background scheduler should set this. API layer uses current user.",
    )
    symbols: list[str] | None = Field(
        default=None,
        description="Optional symbol filter. Defaults to current user's watchlist.",
    )
    market: MarketCode | None = None
    rule_types: list[QuantAlertRuleType] | None = None
    source: QuantAlertScanSource = QuantAlertScanSource.API
    notify: bool = True
    force: bool = False
    max_watchlist_items: int = Field(default=100, ge=1, le=500)

    @field_validator("symbols", mode="before")
    @classmethod
    def normalize_symbols(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None

        normalized: list[str] = []
        seen: set[str] = set()

        for item in value:
            if not isinstance(item, str):
                continue

            symbol = item.strip().upper()
            if not symbol or symbol in seen:
                continue

            normalized.append(symbol)
            seen.add(symbol)

        return normalized or None


class QuantAlertScanItem(BaseModel):
    """单只股票扫描结果。"""

    symbol: str
    market: str
    scanned: bool = True
    triggered_count: int = Field(default=0, ge=0)
    skipped_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    events: list[QuantAlertEventResponse] = Field(default_factory=list)


class QuantAlertScanInputSnapshot(BaseModel):
    """量化提醒扫描输入快照。"""

    source: QuantAlertScanSource
    target_user_id: int
    symbol_count: int = Field(default=0, ge=0)
    rule_type_count: int = Field(default=0, ge=0)
    notify: bool = True
    force: bool = False
    max_watchlist_items: int = Field(default=100, ge=1, le=500)


class QuantAlertScanResponse(BaseModel):
    """量化提醒扫描响应体。"""

    status: QuantAlertScanStatus
    unavailable_reason: QuantAlertUnavailableReason | None = None
    summary: str
    scanned_count: int = Field(default=0, ge=0)
    triggered_count: int = Field(default=0, ge=0)
    notification_count: int = Field(default=0, ge=0)
    items: list[QuantAlertScanItem] = Field(default_factory=list)
    input_snapshot: QuantAlertScanInputSnapshot
    warnings: list[str] = Field(default_factory=list)
    disclaimer: str = Field(
        default="量化信号提醒仅基于历史行情、技术指标、策略信号和数据质量规则生成，只作为研究线索，不构成投资建议。",
        max_length=500,
    )
