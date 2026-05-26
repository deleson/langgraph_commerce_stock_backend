from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


AIUsageFeature = Literal[
    "stock_analysis",
    "react_reason",
    "react_final_answer",
    "candidate_ai_explanation",
]

AIUsageProvider = Literal[
    "deepseek",
]

AIUsageStatus = Literal[
    "success",
    "failed",
    "blocked",
]

AIUsageTokenSource = Literal[
    "provider_usage",
    "estimated",
    "mixed",
    "none",
]

AIUsageSummaryPeriod = Literal[
    "day",
    "month",
]


class AIUsageLogCreate(BaseModel):
    user_id: int = Field(gt=0)

    feature: AIUsageFeature
    provider: AIUsageProvider = "deepseek"
    model_name: str = Field(min_length=1, max_length=100)

    status: AIUsageStatus = "success"
    token_source: AIUsageTokenSource = "none"

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    estimated_cost: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="CNY", min_length=3, max_length=10)

    request_id: str | None = Field(default=None, max_length=120)
    analysis_thread_id: str | None = Field(default=None, max_length=120)
    trace_id: str | None = Field(default=None, max_length=120)

    error_message: str | None = Field(default=None, max_length=1000)
    extra: dict[str, Any] = Field(default_factory=dict)

    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_total_tokens(self) -> "AIUsageLogCreate":
        calculated_total = self.prompt_tokens + self.completion_tokens
        if self.total_tokens == 0 and calculated_total > 0:
            self.total_tokens = calculated_total
        return self


class AIUsageLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int

    feature: str
    provider: str
    model_name: str

    status: str
    token_source: str

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    estimated_cost: Decimal
    currency: str

    request_id: str | None
    analysis_thread_id: str | None
    trace_id: str | None

    error_message: str | None
    extra: dict[str, Any]

    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None

    created_at: datetime


class AIQuotaAccountCreate(BaseModel):
    user_id: int = Field(gt=0)

    daily_call_limit: int = Field(default=50, ge=0)
    monthly_call_limit: int = Field(default=1000, ge=0)

    daily_token_limit: int = Field(default=100000, ge=0)
    monthly_token_limit: int = Field(default=2000000, ge=0)

    daily_cost_limit: Decimal | None = Field(default=None, ge=0)
    monthly_cost_limit: Decimal | None = Field(default=None, ge=0)

    currency: str = Field(default="CNY", min_length=3, max_length=10)
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=80)

    is_active: bool = True


class AIQuotaAccountUpdate(BaseModel):
    daily_call_limit: int | None = Field(default=None, ge=0)
    monthly_call_limit: int | None = Field(default=None, ge=0)

    daily_token_limit: int | None = Field(default=None, ge=0)
    monthly_token_limit: int | None = Field(default=None, ge=0)

    daily_cost_limit: Decimal | None = Field(default=None, ge=0)
    monthly_cost_limit: Decimal | None = Field(default=None, ge=0)

    currency: str | None = Field(default=None, min_length=3, max_length=10)
    timezone: str | None = Field(default=None, min_length=1, max_length=80)

    is_active: bool | None = None


class AIQuotaAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int

    daily_call_limit: int
    monthly_call_limit: int

    daily_token_limit: int
    monthly_token_limit: int

    daily_cost_limit: Decimal | None
    monthly_cost_limit: Decimal | None

    currency: str
    timezone: str

    is_active: bool

    created_at: datetime
    updated_at: datetime


class AIUsageSummaryCreate(BaseModel):
    user_id: int = Field(gt=0)

    period_type: AIUsageSummaryPeriod
    period_start: date
    period_end: date

    call_count: int = Field(default=0, ge=0)
    success_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    blocked_count: int = Field(default=0, ge=0)

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    estimated_cost: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="CNY", min_length=3, max_length=10)

    @model_validator(mode="after")
    def validate_period_range(self) -> "AIUsageSummaryCreate":
        if self.period_end < self.period_start:
            raise ValueError("period_end must be greater than or equal to period_start")
        return self


class AIUsageSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int

    period_type: str
    period_start: date
    period_end: date

    call_count: int
    success_count: int
    failed_count: int
    blocked_count: int

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    estimated_cost: Decimal
    currency: str

    created_at: datetime
    updated_at: datetime


class AIQuotaRemaining(BaseModel):
    daily_calls_remaining: int | None = None
    monthly_calls_remaining: int | None = None

    daily_tokens_remaining: int | None = None
    monthly_tokens_remaining: int | None = None

    daily_cost_remaining: Decimal | None = None
    monthly_cost_remaining: Decimal | None = None


class AIQuotaSummaryResponse(BaseModel):
    account: AIQuotaAccountResponse

    today: AIUsageSummaryResponse | None = None
    current_month: AIUsageSummaryResponse | None = None

    remaining: AIQuotaRemaining

    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AIQuotaCheckRequest(BaseModel):
    user_id: int = Field(gt=0)

    feature: AIUsageFeature
    provider: AIUsageProvider = "deepseek"
    model_name: str = Field(min_length=1, max_length=100)

    estimated_prompt_tokens: int = Field(default=0, ge=0)
    estimated_completion_tokens: int = Field(default=0, ge=0)
    estimated_total_tokens: int = Field(default=0, ge=0)

    estimated_cost: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="CNY", min_length=3, max_length=10)

    @model_validator(mode="after")
    def validate_estimated_total_tokens(self) -> "AIQuotaCheckRequest":
        calculated_total = self.estimated_prompt_tokens + self.estimated_completion_tokens
        if self.estimated_total_tokens == 0 and calculated_total > 0:
            self.estimated_total_tokens = calculated_total
        return self


class AIQuotaCheckResult(BaseModel):
    allowed: bool

    reason: str | None = Field(default=None, max_length=500)

    account: AIQuotaAccountResponse | None = None
    today: AIUsageSummaryResponse | None = None
    current_month: AIUsageSummaryResponse | None = None
    remaining: AIQuotaRemaining | None = None

    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AIUsageQuery(BaseModel):
    feature: AIUsageFeature | None = None
    status: AIUsageStatus | None = None

    start_date: date | None = None
    end_date: date | None = None

    limit: int = Field(default=50, ge=1, le=200)

    @model_validator(mode="after")
    def validate_date_range(self) -> "AIUsageQuery":
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be greater than or equal to start_date")
        return self


class AIUsageLogListResponse(BaseModel):
    items: list[AIUsageLogResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)