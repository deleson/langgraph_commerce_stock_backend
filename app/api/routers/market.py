from fastapi import APIRouter, Path, Query

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.common import ApiResponse
from app.schemas.market import (
    CandleTimeframe,
    MarketCandleListResponse,
    MarketCode,
    MarketIndicatorResponse,
    MarketOverviewResponse,
    MarketQuoteResponse,
    MarketStockSearchItem,
)
from app.schemas.market_data import AdjustType, MarketDataSource
from app.services.market_service import MarketService
from app.utils.responses import success_response

router = APIRouter(prefix="/market", tags=["market"])


@router.get(
    "/stocks/search",
    summary="Search Stocks",
    response_model=ApiResponse[list[MarketStockSearchItem]],
)
async def search_stocks(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    keyword: str | None = Query(
        default=None,
        max_length=50,
        description="Search keyword for stock symbol or name",
    ),
    market: MarketCode | None = Query(
        default=None,
        description="Optional market filter: US, CN, or HK",
    ),
):
    _ = current_user

    stocks = await MarketService(db).search_stocks(
        keyword=keyword,
        market=market,
    )
    return success_response(data=stocks)


@router.get(
    "/stocks/{symbol}/quote",
    summary="Get Stock Quote",
    response_model=ApiResponse[MarketQuoteResponse],
)
async def get_stock_quote(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    symbol: str = Path(
        min_length=1,
        max_length=20,
        description="Stock symbol, for example AAPL, 600519, or 0700",
    ),
    market: MarketCode = Query(
        default="US",
        description="Market code: US, CN, or HK",
    ),
):
    _ = current_user

    quote = await MarketService(db).get_quote(
        symbol=symbol,
        market=market,
    )
    return success_response(data=quote)


@router.get(
    "/stocks/{symbol}/candles",
    summary="Get Stock Candles",
    response_model=ApiResponse[MarketCandleListResponse],
)
async def get_stock_candles(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    symbol: str = Path(
        min_length=1,
        max_length=20,
        description="Stock symbol, for example AAPL, 600519, or 0700",
    ),
    market: MarketCode = Query(
        default="US",
        description="Market code: US, CN, or HK",
    ),
    timeframe: CandleTimeframe = Query(
        default="1d",
        description="Candle timeframe: 1d, 1h, or 5m",
    ),
    limit: int = Query(
        default=30,
        ge=1,
        le=200,
        description="Number of candles to return",
    ),
):
    _ = current_user

    candles = await MarketService(db).get_candles(
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        limit=limit,
    )
    return success_response(data=candles)


@router.get(
    "/stocks/{symbol}/indicators",
    summary="Get Stock Indicators",
    response_model=ApiResponse[MarketIndicatorResponse],
)
async def get_stock_indicators(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    symbol: str = Path(
        min_length=1,
        max_length=20,
        description="Stock symbol, for example AAPL, 600519, or 0700",
    ),
    market: MarketCode = Query(
        default="US",
        description="Market code: US, CN, or HK",
    ),
):
    _ = current_user

    indicators = await MarketService(db).get_indicators(
        symbol=symbol,
        market=market,
    )
    return success_response(data=indicators)


@router.get(
    "/stocks/{symbol}/overview",
    summary="Get Stock Overview",
    response_model=ApiResponse[MarketOverviewResponse],
)
async def get_stock_overview(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    symbol: str = Path(
        min_length=1,
        max_length=20,
        description="Stock symbol, for example AAPL, 600519, or 0700",
    ),
    market: MarketCode = Query(
        default="US",
        description="Market code: US, CN, or HK",
    ),
    timeframe: CandleTimeframe = Query(
        default="1d",
        description="Candle timeframe: 1d, 1h, or 5m",
    ),
    limit: int = Query(
        default=30,
        ge=1,
        le=200,
        description="Number of candles to include in overview",
    ),
    include_technical_indicators: bool = Query(
        default=False,
        description="Whether to include full technical indicator summary",
    ),
    technical_indicator_limit: int = Query(
        default=120,
        ge=35,
        le=1000,
        description="Number of candles used for technical indicator calculation",
    ),
    adjust_type: AdjustType = Query(
        default="none",
        description="Adjustment type for technical indicators",
    ),
    technical_indicator_source: MarketDataSource | None = Query(
        default=None,
        description="Optional data source for technical indicators",
    ),
    include_data_quality: bool = Query(
        default=False,
        description="Whether to include market data quality report",
    ),
    include_sync_status: bool = Query(
        default=False,
        description="Whether to include latest market data sync status",
    ),
    data_quality_source: MarketDataSource | None = Query(
        default=None,
        description="Optional data source for quality and sync status, for example baostock or tushare",
    ),
    data_quality_min_required: int = Query(
        default=1,
        ge=1,
        le=1000,
        description="Minimum candle count required for data quality check",
    ),
    data_quality_stale_after_days: int | None = Query(
        default=None,
        ge=1,
        le=3650,
        description="Mark data as stale if latest candle is older than this many days",
    ),
    include_strategy_signal: bool = Query(
        default=False,
        description="Whether to include strategy signal summary",
    ),
    strategy_signal_limit: int = Query(
        default=120,
        ge=35,
        le=1000,
        description="Number of candles used for strategy signal calculation",
    ),
    strategy_signal_source: MarketDataSource | None = Query(
        default=None,
        description="Optional data source for strategy signal",
    ),
    strategy_signal_include_detail: bool = Query(
        default=True,
        description="Whether to include strategy rule details",
    ),
    strategy_signal_min_required: int = Query(
        default=35,
        ge=1,
        le=1000,
        description="Minimum candle count required for strategy signal data quality check",
    ),
    strategy_signal_stale_after_days: int | None = Query(
        default=None,
        ge=1,
        le=3650,
        description="Mark strategy signal data as stale if latest candle is older than this many days",
    ),
):
    _ = current_user

    overview = await MarketService(db).get_overview(
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        limit=limit,
        include_technical_indicators=include_technical_indicators,
        technical_indicator_limit=technical_indicator_limit,
        adjust_type=adjust_type,
        technical_indicator_source=technical_indicator_source,
        include_data_quality=include_data_quality,
        include_sync_status=include_sync_status,
        data_quality_source=data_quality_source,
        data_quality_min_required=data_quality_min_required,
        data_quality_stale_after_days=data_quality_stale_after_days,
        include_strategy_signal=include_strategy_signal,
        strategy_signal_limit=strategy_signal_limit,
        strategy_signal_source=strategy_signal_source,
        strategy_signal_include_detail=strategy_signal_include_detail,
        strategy_signal_min_required=strategy_signal_min_required,
        strategy_signal_stale_after_days=strategy_signal_stale_after_days,
    )
    return success_response(data=overview)
