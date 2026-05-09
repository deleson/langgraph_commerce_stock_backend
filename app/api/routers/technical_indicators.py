from fastapi import APIRouter, Path, Query

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.common import ApiResponse
from app.schemas.market_data import AdjustType, CandleTimeframe, MarketCode, MarketDataSource
from app.schemas.technical_indicator import (
    MacdSnapshot,
    MomentumSnapshot,
    MovingAverageSnapshot,
    RsiSnapshot,
    TechnicalIndicatorResponse,
    VolatilitySnapshot,
    VolumeFactorSnapshot,
)
from app.services.technical_indicator_query_service import TechnicalIndicatorQueryService
from app.utils.responses import success_response


router = APIRouter(prefix="/technical-indicators", tags=["technical-indicators"])


@router.get(
    "/stocks/{symbol}/summary",
    summary="Get Technical Indicator Summary",
    response_model=ApiResponse[TechnicalIndicatorResponse],
)
async def get_technical_indicator_summary(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    symbol: str = Path(min_length=1, max_length=20),
    market: MarketCode = Query(default="CN"),
    timeframe: CandleTimeframe = Query(default="1d"),
    limit: int = Query(default=120, ge=35, le=1000),
    adjust_type: AdjustType = Query(default="none"),
    source: MarketDataSource | None = Query(default=None),
):
    _ = current_user

    result = await TechnicalIndicatorQueryService(db).get_summary(
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        limit=limit,
        adjust_type=adjust_type,
        source=source,
    )
    return success_response(data=result)


@router.get(
    "/stocks/{symbol}/ma",
    summary="Get Moving Average Indicators",
    response_model=ApiResponse[MovingAverageSnapshot],
)
async def get_moving_average(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    symbol: str = Path(min_length=1, max_length=20),
    market: MarketCode = Query(default="CN"),
    timeframe: CandleTimeframe = Query(default="1d"),
    limit: int = Query(default=120, ge=5, le=1000),
    adjust_type: AdjustType = Query(default="none"),
    source: MarketDataSource | None = Query(default=None),
):
    _ = current_user

    result = await TechnicalIndicatorQueryService(db).get_moving_average(
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        limit=limit,
        adjust_type=adjust_type,
        source=source,
    )
    return success_response(data=result)


@router.get(
    "/stocks/{symbol}/rsi",
    summary="Get RSI Indicator",
    response_model=ApiResponse[RsiSnapshot],
)
async def get_rsi(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    symbol: str = Path(min_length=1, max_length=20),
    market: MarketCode = Query(default="CN"),
    timeframe: CandleTimeframe = Query(default="1d"),
    limit: int = Query(default=120, ge=7, le=1000),
    adjust_type: AdjustType = Query(default="none"),
    source: MarketDataSource | None = Query(default=None),
):
    _ = current_user

    result = await TechnicalIndicatorQueryService(db).get_rsi(
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        limit=limit,
        adjust_type=adjust_type,
        source=source,
    )
    return success_response(data=result)


@router.get(
    "/stocks/{symbol}/macd",
    summary="Get MACD Indicator",
    response_model=ApiResponse[MacdSnapshot],
)
async def get_macd(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    symbol: str = Path(min_length=1, max_length=20),
    market: MarketCode = Query(default="CN"),
    timeframe: CandleTimeframe = Query(default="1d"),
    limit: int = Query(default=120, ge=35, le=1000),
    adjust_type: AdjustType = Query(default="none"),
    source: MarketDataSource | None = Query(default=None),
):
    _ = current_user

    result = await TechnicalIndicatorQueryService(db).get_macd(
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        limit=limit,
        adjust_type=adjust_type,
        source=source,
    )
    return success_response(data=result)


@router.get(
    "/stocks/{symbol}/volatility",
    summary="Get Volatility Factor",
    response_model=ApiResponse[VolatilitySnapshot],
)
async def get_volatility(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    symbol: str = Path(min_length=1, max_length=20),
    market: MarketCode = Query(default="CN"),
    timeframe: CandleTimeframe = Query(default="1d"),
    limit: int = Query(default=120, ge=3, le=1000),
    adjust_type: AdjustType = Query(default="none"),
    source: MarketDataSource | None = Query(default=None),
):
    _ = current_user

    result = await TechnicalIndicatorQueryService(db).get_volatility(
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        limit=limit,
        adjust_type=adjust_type,
        source=source,
    )
    return success_response(data=result)


@router.get(
    "/stocks/{symbol}/momentum",
    summary="Get Momentum Factor",
    response_model=ApiResponse[MomentumSnapshot],
)
async def get_momentum(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    symbol: str = Path(min_length=1, max_length=20),
    market: MarketCode = Query(default="CN"),
    timeframe: CandleTimeframe = Query(default="1d"),
    limit: int = Query(default=120, ge=6, le=1000),
    adjust_type: AdjustType = Query(default="none"),
    source: MarketDataSource | None = Query(default=None),
):
    _ = current_user

    result = await TechnicalIndicatorQueryService(db).get_momentum(
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        limit=limit,
        adjust_type=adjust_type,
        source=source,
    )
    return success_response(data=result)


@router.get(
    "/stocks/{symbol}/volume",
    summary="Get Volume Factor",
    response_model=ApiResponse[VolumeFactorSnapshot],
)
async def get_volume_factor(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    symbol: str = Path(min_length=1, max_length=20),
    market: MarketCode = Query(default="CN"),
    timeframe: CandleTimeframe = Query(default="1d"),
    limit: int = Query(default=120, ge=5, le=1000),
    adjust_type: AdjustType = Query(default="none"),
    source: MarketDataSource | None = Query(default=None),
):
    _ = current_user

    result = await TechnicalIndicatorQueryService(db).get_volume_factor(
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        limit=limit,
        adjust_type=adjust_type,
        source=source,
    )
    return success_response(data=result)