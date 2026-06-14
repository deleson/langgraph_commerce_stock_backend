"""纸面交易 Schema。

纸面交易只表示未来模拟盘：虚拟账户、虚拟订单、虚拟成交、模拟持仓和权益曲线。
本模块的数据结构不会连接券商，也不会产生真实下单行为。
"""

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
    """纸面交易账户状态。"""

    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


class PaperTradingOrderSide(StrEnum):
    """纸面交易订单方向。"""

    BUY = "buy"
    SELL = "sell"


class PaperTradingOrderStatus(StrEnum):
    """纸面交易订单状态。"""

    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class PaperTradingSignalSource(StrEnum):
    """生成纸面交易订单所依据的信号来源。"""

    STRATEGY_SIGNAL = "strategy_signal"
    QUANT_ALERT = "quant_alert"
    MANUAL = "manual"


class PaperTradingTickSource(StrEnum):
    """纸面交易 tick 的触发来源。"""

    MANUAL = "manual"
    API = "api"
    BACKGROUND_TASK = "background_task"
    SCHEDULER = "scheduler"


class PaperTradingTickStatus(StrEnum):
    """纸面交易 tick 执行状态。"""

    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"

class PaperTradingRunStatus(StrEnum):
    """纸面交易运行记录状态。"""

    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"

class PaperTradingUnavailableReason(StrEnum):
    """纸面交易 tick 或运行记录不可用原因。"""

    NO_ACCOUNT = "no_account"
    NO_WATCHLIST = "no_watchlist"
    NO_DATA = "no_data"
    DATA_ERROR = "data_error"
    MARKET_CLOSED = "market_closed"
    TICK_FAILED = "tick_failed"


class PaperTradingAccountCreate(BaseModel):
    """创建纸面交易虚拟账户请求体。"""

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
    """更新纸面交易虚拟账户请求体。"""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    status: PaperTradingAccountStatus | None = None


class PaperTradingAccountResponse(BaseModel):
    """纸面交易虚拟账户响应体。"""

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

class PaperTradingAccountConfigBase(BaseModel):
    """纸面交易账户配置基础字段。"""

    is_enabled: bool = True
    max_symbols_per_tick: int = Field(default=50, ge=1, le=500)
    allow_buy: bool = True
    allow_sell: bool = True
    max_single_order_cash_ratio: Decimal = Field(
        default=Decimal("0.10"),
        gt=0,
        le=Decimal("1"),
    )
    max_total_position_ratio: Decimal = Field(
        default=Decimal("0.95"),
        gt=0,
        le=Decimal("1"),
    )
    max_position_count: int = Field(default=20, ge=1, le=500)
    min_order_cash_amount: Decimal = Field(default=Decimal("100"), ge=0)
    fee_rate: Decimal = Field(
        default=Decimal("0.0003"),
        ge=0,
        le=Decimal("0.1"),
    )
    enforce_data_quality: bool = True
    data_quality_stale_after_days: int = Field(default=7, ge=1, le=365)
    notes: str | None = Field(default=None, max_length=500)


class PaperTradingAccountConfigCreate(PaperTradingAccountConfigBase):
    """创建纸面交易账户配置的数据结构。"""

    pass


class PaperTradingAccountConfigUpdate(BaseModel):
    """更新纸面交易账户配置请求体。"""

    is_enabled: bool | None = None
    max_symbols_per_tick: int | None = Field(default=None, ge=1, le=500)
    allow_buy: bool | None = None
    allow_sell: bool | None = None
    max_single_order_cash_ratio: Decimal | None = Field(
        default=None,
        gt=0,
        le=Decimal("1"),
    )
    max_total_position_ratio: Decimal | None = Field(
        default=None,
        gt=0,
        le=Decimal("1"),
    )
    max_position_count: int | None = Field(default=None, ge=1, le=500)
    min_order_cash_amount: Decimal | None = Field(default=None, ge=0)
    fee_rate: Decimal | None = Field(
        default=None,
        ge=0,
        le=Decimal("0.1"),
    )
    enforce_data_quality: bool | None = None
    data_quality_stale_after_days: int | None = Field(default=None, ge=1, le=365)
    notes: str | None = Field(default=None, max_length=500)


class PaperTradingAccountConfigResponse(PaperTradingAccountConfigBase):
    """纸面交易账户配置响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    created_at: datetime
    updated_at: datetime
    disclaimer: str = Field(default=PAPER_TRADING_DISCLAIMER, max_length=300)


class PaperTradingPositionResponse(BaseModel):
    """纸面交易当前模拟持仓响应体。"""

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
    """创建纸面交易虚拟订单的数据结构。"""

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
    """纸面交易虚拟订单响应体。"""

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
    """纸面交易虚拟成交响应体。"""

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
    """纸面交易权益快照响应体。"""

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
    """推进一次纸面交易 tick 的请求体。

    API 层会强制使用路径 account_id 和当前登录用户，避免用户伪造 target_user_id。
    """

    account_id: int | None = None
    target_user_id: int | None = None
    source: PaperTradingTickSource = PaperTradingTickSource.MANUAL
    force: bool = False
    max_symbols: int = Field(default=50, ge=1, le=500)
    notify: bool = False


class PaperTradingTickItem(BaseModel):
    """纸面交易 tick 中单只股票的处理结果。"""

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
    """纸面交易 tick 输入与统计快照。"""

    account_id: int | None = None
    scanned_count: int = Field(ge=0)
    order_count: int = Field(ge=0)
    trade_count: int = Field(ge=0)
    source: PaperTradingTickSource
    data_source: str | None = None


class PaperTradingTickResponse(BaseModel):
    """纸面交易 tick 响应体。"""

    status: PaperTradingTickStatus
    unavailable_reason: PaperTradingUnavailableReason | None = None
    account: PaperTradingAccountResponse | None = None
    run_id: int | None = None
    items: list[PaperTradingTickItem] = Field(default_factory=list)
    equity_snapshot: PaperTradingEquitySnapshotResponse | None = None
    input_snapshot: PaperTradingTickInputSnapshot | None = None
    warnings: list[str] = Field(default_factory=list, max_length=20)
    generated_at: datetime
    disclaimer: str = Field(default=PAPER_TRADING_DISCLAIMER, max_length=300)

class PaperTradingRunCreate(BaseModel):
    """创建纸面交易运行记录的数据结构。"""

    account_id: int
    source: PaperTradingTickSource
    request_snapshot: dict[str, Any] = Field(default_factory=dict)
    account_config_snapshot: dict[str, Any] = Field(default_factory=dict)


class PaperTradingRunUpdate(BaseModel):
    """更新纸面交易运行记录的数据结构。"""

    status: PaperTradingRunStatus
    unavailable_reason: PaperTradingUnavailableReason | None = None
    scanned_count: int = Field(default=0, ge=0)
    actionable_count: int = Field(default=0, ge=0)
    order_count: int = Field(default=0, ge=0)
    trade_count: int = Field(default=0, ge=0)
    skipped_count: int = Field(default=0, ge=0)
    equity_snapshot_id: int | None = None
    warnings: list[str] = Field(default_factory=list, max_length=50)
    errors: list[str] = Field(default_factory=list, max_length=50)
    signal_snapshot: dict[str, Any] = Field(default_factory=dict)
    execution_snapshot: dict[str, Any] = Field(default_factory=dict)
    position_snapshot: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int | None = Field(default=None, ge=0)


class PaperTradingRunResponse(BaseModel):
    """纸面交易运行记录响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    status: PaperTradingRunStatus
    source: PaperTradingTickSource
    unavailable_reason: PaperTradingUnavailableReason | None = None
    scanned_count: int
    actionable_count: int
    order_count: int
    trade_count: int
    skipped_count: int
    equity_snapshot_id: int | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: int | None = None
    created_at: datetime
    updated_at: datetime
    disclaimer: str = Field(default=PAPER_TRADING_DISCLAIMER, max_length=300)


class PaperTradingRunDetailResponse(PaperTradingRunResponse):
    """纸面交易运行记录详情响应体。"""

    request_snapshot: dict[str, Any] = Field(default_factory=dict)
    account_config_snapshot: dict[str, Any] = Field(default_factory=dict)
    signal_snapshot: dict[str, Any] = Field(default_factory=dict)
    execution_snapshot: dict[str, Any] = Field(default_factory=dict)
    position_snapshot: dict[str, Any] = Field(default_factory=dict)
    equity_snapshot: PaperTradingEquitySnapshotResponse | None = None

class PaperTradingAccountDetailResponse(BaseModel):
    """纸面交易账户详情聚合响应。"""

    account: PaperTradingAccountResponse
    config: PaperTradingAccountConfigResponse | None = None
    positions: list[PaperTradingPositionResponse] = Field(default_factory=list)
    latest_equity: PaperTradingEquitySnapshotResponse | None = None
    latest_run: PaperTradingRunResponse | None = None

class PaperTradingListQuery(BaseModel):
    """纸面交易列表接口通用分页查询。"""

    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class PaperTradingAccountListResponse(BaseModel):
    """纸面交易账户列表响应。"""

    total: int = Field(ge=0)
    items: list[PaperTradingAccountResponse]


class PaperTradingPositionListResponse(BaseModel):
    """纸面交易持仓列表响应。"""

    total: int = Field(ge=0)
    items: list[PaperTradingPositionResponse]


class PaperTradingOrderListResponse(BaseModel):
    """纸面交易订单列表响应。"""

    total: int = Field(ge=0)
    items: list[PaperTradingOrderResponse]


class PaperTradingTradeListResponse(BaseModel):
    """纸面交易成交列表响应。"""

    total: int = Field(ge=0)
    items: list[PaperTradingTradeResponse]


class PaperTradingEquitySnapshotListResponse(BaseModel):
    """纸面交易权益快照列表响应。"""

    total: int = Field(ge=0)
    items: list[PaperTradingEquitySnapshotResponse]

class PaperTradingRunListResponse(BaseModel):
    """纸面交易运行记录列表响应。"""

    total: int = Field(ge=0)
    items: list[PaperTradingRunResponse]
