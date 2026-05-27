from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.market_data import MarketCode
from app.schemas.stock_candidate import (
    StockCandidateGrade,
    StockCandidateRequest,
    StockCandidateResponse,
    StockCandidateUniverseSource,
)


StockCandidateAIExplanationStatus = Literal[
    "available",
    "unavailable",
    "fallback",
]

StockCandidateAIExplanationUnavailableReason = Literal[
    "candidate_scoring_unavailable",
    "empty_candidates",
    "llm_unavailable",
    "llm_error",
    "llm_parse_error",
    "ai_quota_exceeded",
]

StockCandidateAIExplanationStyle = Literal[
    "concise",
    "balanced",
    "detailed",
]

StockCandidateAIResearchPriorityLevel = Literal[
    "high",
    "medium",
    "low",
]


class StockCandidateAIExplanationRequest(BaseModel):
    candidate_request: StockCandidateRequest = Field(
        description=(
            "Original deterministic stock candidate scoring request. "
            "The AI explanation must be based on this scoring result."
        ),
    )

    explanation_style: StockCandidateAIExplanationStyle = Field(
        default="balanced",
        description="AI explanation detail level.",
    )
    max_candidates_to_explain: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of top candidates sent to the AI explanation step.",
    )

    include_comparison: bool = Field(
        default=True,
        description="Whether to ask AI to compare candidates.",
    )
    include_research_priority: bool = Field(
        default=True,
        description="Whether to ask AI to generate research priority ordering.",
    )
    include_risk_summary: bool = Field(
        default=True,
        description="Whether to ask AI to summarize overall risks.",
    )

    allow_fallback: bool = Field(
        default=True,
        description=(
            "When LLM is unavailable or parsing fails, return a deterministic "
            "fallback explanation instead of failing the whole request."
        ),
    )

    @model_validator(mode="after")
    def validate_candidate_request_for_ai_explanation(
        self,
    ) -> "StockCandidateAIExplanationRequest":
        if self.max_candidates_to_explain > self.candidate_request.top_n:
            raise ValueError(
                "max_candidates_to_explain must be less than or equal to candidate_request.top_n"
            )
        return self


class StockCandidateAIExplanationItem(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    market: MarketCode
    name: str | None = Field(default=None, max_length=100)

    rank: int | None = Field(default=None, ge=1)
    score: int = Field(ge=0, le=100)
    grade: StockCandidateGrade

    explanation: str = Field(
        min_length=1,
        max_length=1200,
        description="AI-generated Chinese explanation for this candidate.",
    )
    key_strengths: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Main research strengths summarized by AI.",
    )
    key_risks: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Main risks summarized by AI.",
    )
    research_focus: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Suggested research focus points, not investment advice.",
    )


class StockCandidateAIComparisonItem(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    market: MarketCode

    compared_with: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Other symbols compared with this candidate.",
    )
    relative_strengths: list[str] = Field(default_factory=list, max_length=5)
    relative_weaknesses: list[str] = Field(default_factory=list, max_length=5)
    comparison_summary: str = Field(min_length=1, max_length=1000)


class StockCandidateAIResearchPriorityItem(BaseModel):
    priority_rank: int = Field(ge=1)
    priority_level: StockCandidateAIResearchPriorityLevel

    symbol: str = Field(min_length=1, max_length=20)
    market: MarketCode
    grade: StockCandidateGrade
    score: int = Field(ge=0, le=100)

    reason: str = Field(
        min_length=1,
        max_length=800,
        description="Why this candidate has this research priority.",
    )
    suggested_next_steps: list[str] = Field(default_factory=list, max_length=5)


class StockCandidateAIRiskSummary(BaseModel):
    overall_risk_level: StockCandidateAIResearchPriorityLevel = Field(
        description="High means risk is high, not research priority high.",
    )
    summary: str = Field(min_length=1, max_length=1200)
    key_risks: list[str] = Field(default_factory=list, max_length=8)
    risk_controls: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Research-oriented risk control reminders.",
    )


class StockCandidateAIExplanationInputSnapshot(BaseModel):
    universe_source: StockCandidateUniverseSource
    requested_top_n: int = Field(ge=1)
    candidate_count: int = Field(ge=0)
    explained_candidate_count: int = Field(ge=0)

    explanation_style: StockCandidateAIExplanationStyle = "balanced"
    include_comparison: bool = True
    include_research_priority: bool = True
    include_risk_summary: bool = True

    score_formula_versions: list[str] = Field(default_factory=list, max_length=10)
    ai_context_truncated: bool = False


class StockCandidateAIExplanationResponse(BaseModel):
    status: StockCandidateAIExplanationStatus = "available"
    unavailable_reason: StockCandidateAIExplanationUnavailableReason | None = None

    ai_used: bool = Field(
        default=True,
        description="Whether the response was generated by LLM.",
    )
    fallback_reason: str | None = Field(
        default=None,
        max_length=500,
        description="Reason for deterministic fallback when ai_used is false.",
    )

    summary: str = Field(min_length=1, max_length=1500)

    candidate_explanations: list[StockCandidateAIExplanationItem] = Field(
        default_factory=list,
        max_length=10,
    )
    comparisons: list[StockCandidateAIComparisonItem] = Field(
        default_factory=list,
        max_length=10,
    )
    research_priorities: list[StockCandidateAIResearchPriorityItem] = Field(
        default_factory=list,
        max_length=10,
    )
    risk_summary: StockCandidateAIRiskSummary | None = None

    source_candidate_result: StockCandidateResponse | None = Field(
        default=None,
        description=(
            "Original deterministic candidate scoring result. "
            "This keeps AI explanation traceable to rule-based scoring."
        ),
    )
    input_snapshot: StockCandidateAIExplanationInputSnapshot | None = None

    warnings: list[str] = Field(default_factory=list, max_length=30)

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    disclaimer: str = Field(
        default=(
            "本 AI 候选解释仅基于系统已生成的量化候选评分结果进行中文解释、"
            "候选对比和研究优先级总结，只能作为研究线索，"
            "不构成投资建议，也不承诺未来收益。"
        ),
        max_length=300,
    )