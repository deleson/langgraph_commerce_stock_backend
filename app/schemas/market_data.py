from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


MarketCode = Literal["US", "CN", "HK"]
CandleTimeframe = Literal["1d", "1h", "5m"]
MarketDataSource = Literal[
    "mock",
    "baostock",
    "akshare",
    "tushare",
    "alpha_vantage",
    "polygon",
]
AdjustType = Literal["none", "qfq", "hfq"]


class MarketSymbolCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    market: MarketCode
    name: str = Field(min_length=1, max_length=100)
    currency: str = Field(min_length=1, max_length=10)
    exchange: str | None = Field(default=None, max_length=30)
    provider_symbol: str | None = Field(default=None, max_length=50)
    source: MarketDataSource = "mock"
    is_active: bool = True

    @field_validator("symbol", "market", "currency", "exchange", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("provider_symbol", mode="before")
    @classmethod
    def normalize_provider_symbol(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value


class MarketSymbolUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    currency: str | None = Field(default=None, min_length=1, max_length=10)
    exchange: str | None = Field(default=None, max_length=30)
    provider_symbol: str | None = Field(default=None, max_length=50)
    source: MarketDataSource | None = None
    is_active: bool | None = None

    @field_validator("currency", "exchange", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("name", "provider_symbol", mode="before")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip()
        return value


class MarketSymbolDB(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    market: str
    name: str
    currency: str
    exchange: str | None
    provider_symbol: str | None
    source: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class MarketCandleCreate(BaseModel):
    symbol_id: int | None = None
    symbol: str = Field(min_length=1, max_length=20)
    market: MarketCode
    timeframe: CandleTimeframe = "1d"
    candle_time: datetime
    open_price: Decimal = Field(ge=0)
    high_price: Decimal = Field(ge=0)
    low_price: Decimal = Field(ge=0)
    close_price: Decimal = Field(ge=0)
    volume: int = Field(default=0, ge=0)
    amount: Decimal | None = Field(default=None, ge=0)
    source: MarketDataSource = "mock"
    is_adjusted: bool = False
    adjust_type: AdjustType = "none"

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("high_price")
    @classmethod
    def validate_high_price(
        cls,
        value: Decimal,
    ) -> Decimal:
        return value

    @field_validator("low_price")
    @classmethod
    def validate_low_price(
        cls,
        value: Decimal,
    ) -> Decimal:
        return value


class MarketCandleDB(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol_id: int | None
    symbol: str
    market: str
    timeframe: str
    candle_time: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: int
    amount: Decimal | None
    source: str
    is_adjusted: bool
    adjust_type: str
    created_at: datetime
    updated_at: datetime


class MarketCandleQuery(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    market: MarketCode
    timeframe: CandleTimeframe = "1d"
    limit: int = Field(default=250, ge=1, le=1000)
    adjust_type: AdjustType = "none"
    source: MarketDataSource | None = None

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class MarketProviderCandle(BaseModel):
    symbol: str
    market: MarketCode
    timeframe: CandleTimeframe = "1d"
    candle_time: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: int = 0
    amount: Decimal | None = None
    source: MarketDataSource
    is_adjusted: bool = False
    adjust_type: AdjustType = "none"

    @field_validator("symbol", "market", mode="before")
    @classmethod
    def normalize_uppercase(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value