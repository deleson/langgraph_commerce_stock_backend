from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.market_data import MarketCode


PAPER_TRADING_DISCLAIMER = (
    "纸面交易仅用于研究和学习，不是真实交易，不构成投资建议，也不承诺未来收益。"
)


class PaperTradingAccountStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


class PaperTradingOrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class PaperTradingOrderStatus(StrEnum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class PaperTradingSignalSource(StrEnum):
    STRATEGY_SIGNAL = "strategy_signal"
    QUANT_ALERT = "quant_alert"
    MANUAL = "manual"


class PaperTradingTickSource(StrEnum):
    MANUAL = "manual"
    API = "api"
    BACKGROUND_TASK = "background_task"
    SCHEDULER = "scheduler"


class PaperTradingTickStatus(StrEnum):
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class PaperTradingUnavailableReason(StrEnum):
    NO_ACCOUNT = "no_account"
    NO_WATCHLIST = "no_watchlist"
    NO_DATA = "no_data"
    DATA_ERROR = "data_error"
    MARKET_CLOSED = "market_closed"
    TICK_FAILED = "tick_failed"


class PaperTradingAccountCreate(BaseModel):
    name: str = Field(default="默认纸面交易账户", min_length=1, max_length=120)
    initial_cash: Decimal = Field(default=Decimal("100000"), gt=0)
    currency: str = Field(default="CNY", min_length=3, max_length=8)

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class PaperTradingAccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    status: PaperTradingAccountStatus | None = None


class PaperTradingAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    initial_cash: Decimal
    cash_balance: Decimal
    currency: str
    status: PaperTradingAccountStatus
    created_at: datetime
    updated_at: datetime
    disclaimer: str = Field(default=PAPER_TRADING_DISCLAIMER, max_length=300)


class PaperTradingPositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    symbol: str
    market: str
    quantity: Decimal
    avg_cost: Decimal
    last_price: Decimal | None = None
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_return: float | None = None
    updated_at: datetime

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class PaperTradingOrderCreate(BaseModel):
    account_id: int
    symbol: str = Field(min_length=1, max_length=32)
    market: MarketCode
    side: PaperTradingOrderSide
    planned_quantity: Decimal = Field(gt=0)
    planned_price: Decimal | None = Field(default=None, gt=0)
    signal_source: PaperTradingSignalSource
    signal_snapshot: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class PaperTradingOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    symbol: str
    market: str
    side: PaperTradingOrderSide
    status: PaperTradingOrderStatus
    planned_quantity: Decimal
    planned_price: Decimal | None = None
    filled_quantity: Decimal = Decimal("0")
    filled_price: Decimal | None = None
    signal_source: PaperTradingSignalSource
    signal_snapshot: dict[str, Any] = Field(default_factory=dict)
    reason: str
    created_at: datetime
    updated_at: datetime


class PaperTradingTradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    order_id: int | None = None
    symbol: str
    market: str
    side: PaperTradingOrderSide
    filled_quantity: Decimal
    filled_price: Decimal
    trade_value: Decimal
    fee_amount: Decimal = Decimal("0")
    traded_at: datetime


class PaperTradingEquitySnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    snapshot_date: date
    cash_balance: Decimal
    position_market_value: Decimal
    total_equity: Decimal
    total_return: float
    daily_return: float | None = None
    max_drawdown: float | None = None
    created_at: datetime


class PaperTradingTickRequest(BaseModel):
    account_id: int | None = None
    target_user_id: int | None = None
    source: PaperTradingTickSource = PaperTradingTickSource.MANUAL
    force: bool = False
    max_symbols: int = Field(default=50, ge=1, le=500)
    notify: bool = False


class PaperTradingTickItem(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    market: MarketCode
    action: str = Field(max_length=32)
    order_id: int | None = None
    trade_id: int | None = None
    message: str = Field(min_length=1, max_length=500)
    warnings: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class PaperTradingTickInputSnapshot(BaseModel):
    account_id: int | None = None
    scanned_count: int = Field(ge=0)
    order_count: int = Field(ge=0)
    trade_count: int = Field(ge=0)
    source: PaperTradingTickSource
    data_source: str | None = None


class PaperTradingTickResponse(BaseModel):
    status: PaperTradingTickStatus
    unavailable_reason: PaperTradingUnavailableReason | None = None
    account: PaperTradingAccountResponse | None = None
    items: list[PaperTradingTickItem] = Field(default_factory=list)
    equity_snapshot: PaperTradingEquitySnapshotResponse | None = None
    input_snapshot: PaperTradingTickInputSnapshot | None = None
    warnings: list[str] = Field(default_factory=list, max_length=20)
    generated_at: datetime
    disclaimer: str = Field(default=PAPER_TRADING_DISCLAIMER, max_length=300)


class PaperTradingAccountDetailResponse(BaseModel):
    account: PaperTradingAccountResponse
    positions: list[PaperTradingPositionResponse] = Field(default_factory=list)
    latest_equity: PaperTradingEquitySnapshotResponse | None = None
    disclaimer: str = Field(default=PAPER_TRADING_DISCLAIMER, max_length=300)


class PaperTradingListQuery(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class PaperTradingAccountListResponse(BaseModel):
    total: int = Field(ge=0)
    items: list[PaperTradingAccountResponse]


class PaperTradingPositionListResponse(BaseModel):
    total: int = Field(ge=0)
    items: list[PaperTradingPositionResponse]


class PaperTradingOrderListResponse(BaseModel):
    total: int = Field(ge=0)
    items: list[PaperTradingOrderResponse]


class PaperTradingTradeListResponse(BaseModel):
    total: int = Field(ge=0)
    items: list[PaperTradingTradeResponse]


class PaperTradingEquitySnapshotListResponse(BaseModel):
    total: int = Field(ge=0)
    items: list[PaperTradingEquitySnapshotResponse]