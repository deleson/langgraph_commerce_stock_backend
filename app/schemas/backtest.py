from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.market_data import (
    AdjustType,
    CandleTimeframe,
    MarketCode,
    MarketDataSource,
)
from app.schemas.strategy_signal import (
    StrategySignalAction,
    StrategySignalStrength,
)


BacktestStatus = Literal["available", "unavailable"]
BacktestTradeAction = Literal["buy", "sell"]
BacktestPositionStatus = Literal["cash", "long"]
BacktestExecutionPriceType = Literal["next_open"]
BacktestDecisionAction = Literal["buy", "sell", "hold", "observe", "skip"]
BacktestUnavailableReason = Literal[
    "no_data",
    "insufficient_data",
    "data_error",
    "invalid_date_range",
]


class BacktestRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20, examples=["600519"])
    market: MarketCode = Field(examples=["CN"])
    start_date: date
    end_date: date

    timeframe: CandleTimeframe = "1d"
    initial_cash: Decimal = Field(default=Decimal("100000"), gt=0)
    position_size_ratio: float = Field(default=1.0, gt=0, le=1)

    adjust_type: AdjustType = "none"
    source: MarketDataSource | None = None
    min_required_candles: int = Field(default=60, ge=30, le=1000)
    enforce_data_quality: bool = True
    data_quality_stale_after_days: int | None = Field(default=None, ge=1, le=3650)

    include_trades: bool = True
    include_daily_equity: bool = True
    include_signal_snapshots: bool = False

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @model_validator(mode="after")
    def validate_date_range(self) -> "BacktestRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be greater than or equal to start_date")
        return self


class BacktestTrade(BaseModel):
    sequence_no: int = Field(ge=1)
    action: BacktestTradeAction
    trade_date: date

    price: Decimal = Field(gt=0)
    quantity: int = Field(gt=0)
    signal_date: date | None = None
    execution_price_type: BacktestExecutionPriceType = "next_open"
    trade_value: Decimal = Field(ge=0)

    cash_before: Decimal = Field(ge=0)
    cash_after: Decimal = Field(ge=0)
    position_before: int = Field(ge=0)
    position_after: int = Field(ge=0)
    equity_after: Decimal = Field(ge=0)

    realized_pnl: Decimal | None = None
    realized_return: float | None = None
    holding_days: int | None = Field(default=None, ge=0)

    signal: StrategySignalAction | None = None
    signal_strength: StrategySignalStrength | None = None
    signal_score: int | None = Field(default=None, ge=0, le=100)

    reason: str = Field(min_length=1, max_length=500)

class BacktestDailyEquity(BaseModel):
    trade_date: date
    close_price: Decimal = Field(ge=0)

    cash: Decimal = Field(ge=0)
    position_quantity: int = Field(ge=0)
    position_market_value: Decimal = Field(ge=0)
    total_equity: Decimal = Field(ge=0)

    daily_return: float | None = None
    drawdown: float = Field(default=0, ge=0)


class BacktestSignalSnapshot(BaseModel):
    trade_date: date
    decision: BacktestDecisionAction

    signal: StrategySignalAction | None = None
    signal_strength: StrategySignalStrength | None = None
    signal_score: int | None = Field(default=None, ge=0, le=100)

    close_price: Decimal = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)
    warnings: list[str] = Field(default_factory=list, max_length=10)


class BacktestMetrics(BaseModel):
    initial_cash: Decimal = Field(gt=0)
    final_equity: Decimal = Field(ge=0)

    total_return: float
    annualized_return: float | None = None
    average_daily_return: float | None = None

    max_drawdown: float = Field(ge=0)
    daily_return_volatility: float | None = Field(default=None, ge=0)
    annualized_volatility: float | None = Field(default=None, ge=0)
    sharpe_ratio: float | None = None
    return_drawdown_ratio: float | None = None

    trade_count: int = Field(ge=0)
    buy_count: int = Field(ge=0)
    sell_count: int = Field(ge=0)

    completed_trade_count: int = Field(ge=0)
    winning_trade_count: int = Field(ge=0)
    losing_trade_count: int = Field(ge=0)
    win_rate: float | None = Field(default=None, ge=0, le=1)

    average_win: Decimal | None = None
    average_loss: Decimal | None = None
    profit_loss_ratio: float | None = None
    average_realized_return: float | None = None
    best_trade_pnl: Decimal | None = None
    worst_trade_pnl: Decimal | None = None

    holding_days: int = Field(ge=0)
    cash_days: int = Field(ge=0)
    average_holding_days: float | None = Field(default=None, ge=0)

    buy_and_hold_return: float | None = None
    excess_return: float | None = None
    outperformed_buy_and_hold: bool | None = None


class BacktestInputSnapshot(BaseModel):
    candle_count: int = Field(ge=0)
    first_candle_date: date | None = None
    last_candle_date: date | None = None

    strategy_name: str = Field(default="strategy_signal_v1", max_length=80)
    timeframe: CandleTimeframe = "1d"
    adjust_type: AdjustType = "none"
    source: MarketDataSource | str | None = None

    min_required_candles: int = Field(ge=1)
    position_size_ratio: float = Field(gt=0, le=1)


class BacktestResponse(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    market: MarketCode
    start_date: date
    end_date: date

    status: BacktestStatus = "available"
    unavailable_reason: BacktestUnavailableReason | None = None

    summary: str = Field(min_length=1, max_length=800)
    metrics: BacktestMetrics | None = None

    trades: list[BacktestTrade] = Field(default_factory=list)
    daily_equity: list[BacktestDailyEquity] = Field(default_factory=list)
    signal_snapshots: list[BacktestSignalSnapshot] = Field(default_factory=list)

    input_snapshot: BacktestInputSnapshot | None = None
    warnings: list[str] = Field(default_factory=list, max_length=20)
    calculated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    disclaimer: str = Field(
        default="本回测仅基于历史行情和策略规则进行模拟，不构成投资建议，也不代表未来收益。",
        max_length=300,
    )

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value