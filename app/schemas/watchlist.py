"""自选股 Schema。

本文件定义用户自选股的创建、更新和响应结构。
自选股是后续日报、量化提醒、纸面交易扫描股票池的重要来源。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel,ConfigDict,Field,field_validator


MarketCode = Literal["US","CN","HK"]

class WatchlistCreateRequest(BaseModel):
    """创建自选股请求体。"""

    symbol:str = Field(min_length=1,max_length=20)
    market:MarketCode
    name:str | None  = Field(default=None,max_length=100)
    notes:str | None = Field(default=None,max_length=500)
    alert_enabled: bool | None = None

    @field_validator("symbol","market",mode="before")
    @classmethod
    def normalize_uppercase(cls,value:str) -> str:
        if isinstance(value,str):
            return value.strip().upper()
        return value

class WatchlistUpdateRequest(BaseModel):
    """更新自选股设置请求体。"""

    name: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=500)
    alert_enabled: bool | None = None


class WatchlistResponse(BaseModel):
    """自选股响应体。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    market: str
    name: str | None
    notes: str | None
    alert_enabled: bool
    created_at: datetime
    updated_at: datetime
