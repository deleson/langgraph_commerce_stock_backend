from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


MarketCode = Literal["US", "CN", "HK"]
AnalysisType = Literal["stock_basic", "daily_report", "abnormal_alert", "simulation"]
AnalysisStatus = Literal["pending", "running", "completed", "failed"]


class AnalysisRecordCreateRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    market: MarketCode
    analysis_type: AnalysisType = "stock_basic"
    status: AnalysisStatus = "completed"
    summary: str | None = Field(default=None, max_length=500)
    result_snapshot: dict[str, Any] | None = None
    error_message: str | None = None

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class AnalysisRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    market: str
    analysis_type: str
    status: str
    summary: str | None
    result_snapshot: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime