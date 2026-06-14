"""组合回测 Schema。

组合回测用于模拟多资产目标权重、调仓和组合权益曲线。
它是研究工具，不代表真实组合收益，也不构成投资建议。
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.backtest import (
    BacktestExecutionPriceType,
    BacktestRiskControlConfig,
)
from app.schemas.market_data import (
    AdjustType,
    CandleTimeframe,
    MarketCode,
    MarketDataSource,
)


PortfolioBacktestStatus = Literal["available", "unavailable"]

PortfolioBacktestUnavailableReason = Literal[
    "no_data",
    "insufficient_data",
    "data_error",
    "invalid_date_range",
    "invalid_assets",
    "invalid_weights",
]

PortfolioBacktestTradeAction = Literal["buy", "sell"]

PortfolioBacktestTradeReason = Literal[
    "initial_build",
    "rebalance",
    "risk_control",
    "cash_limit",
]

PortfolioBacktestRebalanceFrequency = Literal[
    "none",
    "daily",
    "weekly",
    "monthly",
    "interval",
]


class PortfolioBacktestAsset(BaseModel):
    """组合回测中的单个资产配置。"""

    symbol: str = Field(min_length=1, max_length=20, examples=["600519"])
    market: MarketCode = Field(examples=["CN"])
    target_weight: Decimal = Field(gt=0, le=1)

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class PortfolioBacktestRequest(BaseModel):
    """组合回测请求体。"""

    assets: list[PortfolioBacktestAsset] = Field(min_length=2, max_length=20)
    start_date: date
    end_date: date

    timeframe: CandleTimeframe = "1d"
    initial_cash: Decimal = Field(default=Decimal("100000"), gt=0)
    cash_deploy_ratio: float = Field(default=1.0, gt=0, le=1)

    rebalance_frequency: PortfolioBacktestRebalanceFrequency = "monthly"
    rebalance_interval_days: int | None = Field(default=None, ge=1, le=365)

    risk_control: BacktestRiskControlConfig = Field(
        default_factory=BacktestRiskControlConfig
    )

    adjust_type: AdjustType = "none"
    source: MarketDataSource | None = None
    min_required_candles: int = Field(default=60, ge=30, le=1000)
    enforce_data_quality: bool = True
    data_quality_stale_after_days: int | None = Field(default=None, ge=1, le=3650)

    include_trades: bool = True
    include_daily_equity: bool = True
    include_position_snapshots: bool = True

    @model_validator(mode="after")
    def validate_date_range(self) -> "PortfolioBacktestRequest":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be greater than or equal to start_date")
        return self

    @model_validator(mode="after")
    def validate_unique_assets(self) -> "PortfolioBacktestRequest":
        asset_keys = [(asset.market, asset.symbol) for asset in self.assets]
        if len(asset_keys) != len(set(asset_keys)):
            raise ValueError("assets must not contain duplicate market/symbol pairs")
        return self

    @model_validator(mode="after")
    def validate_target_weights(self) -> "PortfolioBacktestRequest":
        total_weight = sum((asset.target_weight for asset in self.assets), Decimal("0"))
        if abs(total_weight - Decimal("1")) > Decimal("0.0001"):
            raise ValueError("sum of asset target_weight must be 1")
        return self

    @model_validator(mode="after")
    def validate_rebalance_interval(self) -> "PortfolioBacktestRequest":
        if self.rebalance_frequency == "interval" and self.rebalance_interval_days is None:
            raise ValueError(
                "rebalance_interval_days is required when rebalance_frequency is interval"
            )
        return self


class PortfolioBacktestTrade(BaseModel):
    """组合回测中的一笔模拟交易。"""

    sequence_no: int = Field(ge=1)
    symbol: str = Field(min_length=1, max_length=20)
    market: MarketCode

    action: PortfolioBacktestTradeAction
    reason: PortfolioBacktestTradeReason
    trade_date: date

    price: Decimal = Field(gt=0)
    quantity: int = Field(gt=0)
    raw_price: Decimal | None = Field(default=None, gt=0)
    execution_price_type: BacktestExecutionPriceType = "next_open"

    trade_value: Decimal = Field(ge=0)
    commission: Decimal = Field(default=Decimal("0"), ge=0)
    slippage_amount: Decimal = Field(default=Decimal("0"), ge=0)
    slippage_cost: Decimal = Field(default=Decimal("0"), ge=0)

    cash_before: Decimal = Field(ge=0)
    cash_after: Decimal = Field(ge=0)

    position_before: int = Field(ge=0)
    position_after: int = Field(ge=0)

    target_weight: Decimal | None = Field(default=None, ge=0, le=1)
    actual_weight_before: Decimal | None = Field(default=None, ge=0)
    actual_weight_after: Decimal | None = Field(default=None, ge=0)

    portfolio_equity_after: Decimal = Field(ge=0)

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class PortfolioBacktestPositionSnapshot(BaseModel):
    """组合回测某日单资产持仓快照。"""

    symbol: str = Field(min_length=1, max_length=20)
    market: MarketCode

    quantity: int = Field(ge=0)
    close_price: Decimal = Field(ge=0)
    market_value: Decimal = Field(ge=0)

    target_weight: Decimal = Field(ge=0, le=1)
    actual_weight: Decimal = Field(ge=0)

    unrealized_pnl: Decimal | None = None
    unrealized_return: float | None = None

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class PortfolioBacktestDailyEquity(BaseModel):
    """组合回测单日权益曲线节点。"""

    trade_date: date

    cash: Decimal = Field(ge=0)
    position_market_value: Decimal = Field(ge=0)
    total_equity: Decimal = Field(ge=0)

    daily_return: float | None = None
    drawdown: float = Field(default=0, ge=0)

    positions: list[PortfolioBacktestPositionSnapshot] = Field(default_factory=list)


class PortfolioBacktestMetrics(BaseModel):
    """组合回测绩效指标汇总。"""

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
    rebalance_count: int = Field(ge=0)

    total_commission: Decimal = Field(default=Decimal("0"), ge=0)
    total_slippage_cost: Decimal = Field(default=Decimal("0"), ge=0)

    average_cash_ratio: float | None = Field(default=None, ge=0)
    average_position_ratio: float | None = Field(default=None, ge=0)
    turnover_rate: float | None = Field(default=None, ge=0)

    best_day_return: float | None = None
    worst_day_return: float | None = None


class PortfolioBacktestInputSnapshot(BaseModel):
    """组合回测输入参数和数据范围快照。"""

    asset_count: int = Field(ge=0)
    candle_count_by_symbol: dict[str, int] = Field(default_factory=dict)

    first_trade_date: date | None = None
    last_trade_date: date | None = None

    timeframe: CandleTimeframe = "1d"
    adjust_type: AdjustType = "none"
    source: MarketDataSource | str | None = None

    min_required_candles: int = Field(ge=1)
    cash_deploy_ratio: float = Field(gt=0, le=1)
    rebalance_frequency: PortfolioBacktestRebalanceFrequency = "monthly"
    rebalance_interval_days: int | None = None

    target_weights: dict[str, Decimal] = Field(default_factory=dict)
    risk_control: BacktestRiskControlConfig = Field(
        default_factory=BacktestRiskControlConfig
    )


class PortfolioBacktestResponse(BaseModel):
    """组合回测响应体。"""

    assets: list[PortfolioBacktestAsset] = Field(default_factory=list)
    start_date: date
    end_date: date

    status: PortfolioBacktestStatus = "available"
    unavailable_reason: PortfolioBacktestUnavailableReason | None = None

    summary: str = Field(min_length=1, max_length=1000)
    metrics: PortfolioBacktestMetrics | None = None

    trades: list[PortfolioBacktestTrade] = Field(default_factory=list)
    daily_equity: list[PortfolioBacktestDailyEquity] = Field(default_factory=list)

    input_snapshot: PortfolioBacktestInputSnapshot | None = None
    warnings: list[str] = Field(default_factory=list, max_length=30)
    calculated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    disclaimer: str = Field(
        default="本组合回测仅基于历史行情和规则进行模拟，不构成投资建议，也不代表未来收益。",
        max_length=300,
    )
