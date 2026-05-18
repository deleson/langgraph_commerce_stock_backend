from fastapi import APIRouter, Path, Query

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.common import ApiResponse
from app.schemas.market_data import (
    AdjustType,
    CandleTimeframe,
    MarketCode,
    MarketDataSource,
)
from app.schemas.strategy_signal import StrategySignalResponse
from app.services.strategy_signal_query_service import StrategySignalQueryService
from app.utils.responses import success_response


router = APIRouter(prefix="/strategy-signals", tags=["strategy-signals"])


@router.get(
    "/stocks/{symbol}",
    summary="Get Stock Strategy Signal",
    response_model=ApiResponse[StrategySignalResponse],
)
async def get_stock_strategy_signal(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    symbol: str = Path(
        min_length=1,
        max_length=20,
        description="Stock symbol, for example AAPL, 600519, or 0700",
    ),
    market: MarketCode = Query(
        default="CN",
        description="Market code: US, CN, or HK",
    ),
    timeframe: CandleTimeframe = Query(
        default="1d",
        description="Candle timeframe, currently usually 1d",
    ),
    limit: int = Query(
        default=120,
        ge=35,
        le=1000,
        description="Number of candles used for technical indicator calculation",
    ),
    adjust_type: AdjustType = Query(
        default="none",
        description="Adjustment type for candles",
    ),
    source: MarketDataSource | None = Query(
        default=None,
        description="Optional market data source, for example mock, baostock, or tushare",
    ),
    include_detail: bool = Query(
        default=True,
        description="Whether to include detailed rule results and input snapshot",
    ),
    min_required: int = Query(
        default=35,
        ge=1,
        le=1000,
        description="Minimum candle count required for data quality check",
    ),
    stale_after_days: int | None = Query(
        default=None,
        ge=1,
        le=3650,
        description="Mark market data as stale if latest candle is older than this many days",
    ),
):
    _ = current_user

    result = await StrategySignalQueryService(db).get_signal(
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        limit=limit,
        adjust_type=adjust_type,
        source=source,
        include_detail=include_detail,
        min_required=min_required,
        stale_after_days=stale_after_days,
    )
    return success_response(data=result)