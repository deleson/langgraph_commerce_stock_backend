"""策略信号 Schema。

策略信号是基于技术指标和数据质量的确定性规则结果，
不是 AI 自由荐股，也不构成投资建议或收益承诺。
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.market_data import (
    AdjustType,
    CandleTimeframe,
    MarketCode,
    MarketDataSource,
)
from app.schemas.market_data_sync import MarketDataQualityReport
from app.schemas.technical_indicator import TechnicalIndicatorResponse


StrategySignalStatus = Literal["available", "unavailable"]
StrategySignalAction = Literal["buy", "sell", "hold", "observe"]
StrategySignalStrength = Literal["weak", "medium", "strong"]
StrategyRuleName = Literal[
    "data_quality",
    "trend",
    "rsi",
    "macd",
    "momentum",
    "volatility",
    "volume",
]
StrategyRuleDirection = Literal[
    "bullish",
    "bearish",
    "neutral",
    "risk",
    "invalid",
]


class StrategySignalRequest(BaseModel):
    """策略信号查询请求体。"""

    symbol: str = Field(min_length=1, max_length=20, examples=["AAPL"])
    market: MarketCode = Field(examples=["US"])
    timeframe: CandleTimeframe = "1d"
    limit: int = Field(default=120, ge=30, le=300)
    adjust_type: AdjustType = "none"
    source: MarketDataSource | None = None
    include_detail: bool = True

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class StrategyRuleResult(BaseModel):
    """单个策略规则维度的评分明细。"""

    rule_name: StrategyRuleName
    direction: StrategyRuleDirection
    score_delta: int = Field(ge=-100, le=100)
    weight: float = Field(default=1.0, ge=0, le=1)
    reason: str = Field(min_length=1, max_length=300)
    warnings: list[str] = Field(default_factory=list, max_length=5)


class StrategySignalInputSnapshot(BaseModel):
    """生成策略信号时使用的输入快照。"""

    technical_indicators: TechnicalIndicatorResponse | None = None
    data_quality: MarketDataQualityReport | None = None


class StrategySignalResponse(BaseModel):
    """策略信号响应体。

    signal / strength / score 只表示当前规则系统的研究信号，
    下游纸面交易也只把它作为虚拟模拟依据。
    """

    symbol: str = Field(min_length=1, max_length=20)
    market: MarketCode
    timeframe: CandleTimeframe
    adjust_type: AdjustType = "none"
    source: MarketDataSource | str | None = None

    status: StrategySignalStatus = "available"
    signal: StrategySignalAction | None = None
    strength: StrategySignalStrength | None = None
    score: int = Field(default=0, ge=0, le=100)

    summary: str = Field(min_length=1, max_length=500)
    reasons: list[str] = Field(default_factory=list, max_length=10)
    risks: list[str] = Field(default_factory=list, max_length=10)
    rule_results: list[StrategyRuleResult] = Field(default_factory=list)

    input_snapshot: StrategySignalInputSnapshot | None = None
    calculated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    disclaimer: str = Field(
        default="本策略信号仅基于历史行情和技术指标规则生成，不构成投资建议，也不承诺未来收益。",
        max_length=300,
    )

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value
