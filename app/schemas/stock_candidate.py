"""候选股票评分 Schema。

候选评分基于数据质量、技术指标、策略信号、风险和用户偏好等规则维度。
结果只表示研究优先级，不是荐股，也不承诺未来收益。
"""

from datetime import UTC, datetime
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


StockCandidateStatus = Literal["available", "unavailable"]

StockCandidateUnavailableReason = Literal[
    "empty_universe",
    "no_candidates",
    "no_data",
    "insufficient_data",
    "invalid_source",
]

StockCandidateUniverseSource = Literal[
    "manual",
    "watchlist",
]

StockCandidateDecision = Literal[
    "candidate",
    "excluded",
]

StockCandidateGrade = Literal[
    "A",
    "B",
    "C",
    "D",
]

StockCandidateScoreDimension = Literal[
    "data_quality",
    "trend",
    "momentum",
    "rsi",
    "macd",
    "volatility",
    "volume",
    "strategy_signal",
    "user_preference",
    "risk",
    "liquidity",
    "backtest_performance",
]


class StockCandidateSymbol(BaseModel):
    """候选股票池中的单只股票。"""

    symbol: str = Field(min_length=1, max_length=20, examples=["600519"])
    market: MarketCode = Field(examples=["CN"])

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class StockCandidateRequest(BaseModel):
    """候选股票评分请求体。"""

    universe_source: StockCandidateUniverseSource = Field(
        default="manual",
        description="Candidate universe source: manual symbols or current user's watchlist.",
    )
    symbols: list[StockCandidateSymbol] = Field(
        default_factory=list,
        max_length=100,
        description="Required when universe_source is manual.",
    )

    top_n: int = Field(default=10, ge=1, le=50)

    timeframe: CandleTimeframe = "1d"
    limit: int = Field(default=120, ge=30, le=300)
    min_required_candles: int = Field(default=60, ge=30, le=300)
    adjust_type: AdjustType = "none"
    source: MarketDataSource | None = None

    enforce_data_quality: bool = True
    data_quality_stale_after_days: int | None = Field(default=None, ge=1, le=3650)

    include_excluded: bool = False
    include_score_breakdown: bool = True
    include_strategy_signal: bool = True
    include_data_quality: bool = True

    @model_validator(mode="after")
    def validate_manual_symbols(self) -> "StockCandidateRequest":
        if self.universe_source == "manual" and not self.symbols:
            raise ValueError("symbols is required when universe_source is manual")
        return self

    @model_validator(mode="after")
    def validate_unique_symbols(self) -> "StockCandidateRequest":
        symbol_keys = [
            (item.market, item.symbol)
            for item in self.symbols
        ]
        if len(symbol_keys) != len(set(symbol_keys)):
            raise ValueError("symbols must not contain duplicate market/symbol pairs")
        return self

    @model_validator(mode="after")
    def validate_min_required_not_greater_than_limit(self) -> "StockCandidateRequest":
        if self.min_required_candles > self.limit:
            raise ValueError("min_required_candles must be less than or equal to limit")
        return self


class StockCandidateScoreRuleResult(BaseModel):
    """候选评分中单个维度的规则结果。"""

    dimension: StockCandidateScoreDimension
    score_delta: int = Field(ge=-100, le=100)
    reason: str = Field(min_length=1, max_length=300)
    warnings: list[str] = Field(default_factory=list, max_length=5)


class StockCandidateScoreBreakdown(BaseModel):
    """候选评分拆解。"""

    formula_version: str = Field(
        default="candidate_scoring_v1",
        min_length=1,
        max_length=50,
    )

    base_score: int = Field(default=50, ge=0, le=100)

    data_quality_score: int = Field(default=0, ge=-100, le=100)
    trend_score: int = Field(default=0, ge=-100, le=100)
    momentum_score: int = Field(default=0, ge=-100, le=100)
    rsi_score: int = Field(default=0, ge=-100, le=100)
    macd_score: int = Field(default=0, ge=-100, le=100)
    volatility_score: int = Field(default=0, ge=-100, le=100)
    volume_score: int = Field(default=0, ge=-100, le=100)
    strategy_signal_score: int = Field(default=0, ge=-100, le=100)
    user_preference_score: int = Field(default=0, ge=-100, le=100)

    risk_score: int = Field(default=0, ge=-100, le=100)
    liquidity_score: int = Field(default=0, ge=-100, le=100)
    backtest_performance_score: int = Field(default=0, ge=-100, le=100)

    raw_score: int | None = Field(default=None, ge=-100, le=200)
    final_score: int = Field(ge=0, le=100)
    rule_results: list[StockCandidateScoreRuleResult] = Field(default_factory=list)

class StockCandidateDataQualitySnapshot(BaseModel):
    """候选股票评分使用的数据质量快照。"""

    status: StockCandidateStatus = "available"
    candle_count: int = Field(default=0, ge=0)
    is_empty: bool = False
    is_enough: bool = True
    is_stale: bool = False
    warnings: list[str] = Field(default_factory=list, max_length=10)
    errors: list[str] = Field(default_factory=list, max_length=10)


class StockCandidateStrategySignalSnapshot(BaseModel):
    """候选股票评分使用的策略信号快照。"""

    status: str = Field(default="unavailable", max_length=30)
    signal: StrategySignalAction | None = None
    strength: StrategySignalStrength | None = None
    score: int | None = Field(default=None, ge=0, le=100)
    summary: str | None = Field(default=None, max_length=300)


class StockCandidateItem(BaseModel):
    """单只候选股票评分结果。"""

    symbol: str = Field(min_length=1, max_length=20)
    market: MarketCode
    name: str | None = Field(default=None, max_length=100)

    decision: StockCandidateDecision = "candidate"
    excluded_reason: str | None = Field(default=None, max_length=300)

    rank: int | None = Field(default=None, ge=1)
    score: int = Field(default=0, ge=0, le=100)
    grade: StockCandidateGrade = "D"

    reasons: list[str] = Field(default_factory=list, max_length=10)
    risks: list[str] = Field(default_factory=list, max_length=10)

    score_breakdown: StockCandidateScoreBreakdown | None = None
    data_quality: StockCandidateDataQualitySnapshot | None = None
    strategy_signal: StockCandidateStrategySignalSnapshot | None = None

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class StockCandidateInputSnapshot(BaseModel):
    """候选评分输入参数和股票池统计快照。"""

    universe_source: StockCandidateUniverseSource
    requested_symbol_count: int = Field(ge=0)
    evaluated_symbol_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)

    top_n: int = Field(ge=1)
    timeframe: CandleTimeframe = "1d"
    limit: int = Field(ge=1)
    min_required_candles: int = Field(ge=1)
    adjust_type: AdjustType = "none"
    source: MarketDataSource | str | None = None

    enforce_data_quality: bool = True


class StockCandidateResponse(BaseModel):
    """候选股票评分响应体。"""

    status: StockCandidateStatus = "available"
    unavailable_reason: StockCandidateUnavailableReason | None = None

    summary: str = Field(min_length=1, max_length=1000)

    candidates: list[StockCandidateItem] = Field(default_factory=list)
    excluded: list[StockCandidateItem] = Field(default_factory=list)

    input_snapshot: StockCandidateInputSnapshot | None = None
    warnings: list[str] = Field(default_factory=list, max_length=30)

    calculated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    disclaimer: str = Field(
        default="本候选股票评分仅基于历史行情、技术指标、策略信号和用户偏好规则生成，只作为研究线索，不构成投资建议，也不承诺未来收益。",
        max_length=300,
    )
