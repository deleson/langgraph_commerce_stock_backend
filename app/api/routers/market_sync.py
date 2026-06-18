"""行情同步 API Router。

该 Router 提供手动同步股票基础信息和 K 线数据的入口。
真实 Provider 调用、数据标准化、去重和落库由 MarketDataSyncService 处理。
"""

from fastapi import APIRouter, Path, Query

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.schemas.common import ApiResponse
from app.schemas.market_data import AdjustType, CandleTimeframe, MarketCode
from app.services.market_data_sync_service import MarketDataSyncService
from app.services.market_symbol_sync_service import MarketSymbolSyncService
from app.utils.responses import success_response


router = APIRouter(prefix="/market-sync", tags=["market-sync"])


@router.post(
    "/symbol-pool",
    summary="Sync Market Symbol Pool",
    response_model=ApiResponse[dict[str, object]],
)
async def sync_market_symbol_pool(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    market: MarketCode = Query(
        default="CN",
        description="Market code: US, CN, or HK",
    ),
    provider: str | None = Query(
        default=None,
        description="Optional Provider name, for example tushare, baostock, or mock",
    ),
    limit: int | None = Query(
        default=None,
        ge=1,
        le=10000,
        description="Optional max number of symbols to sync",
    ),
):
    # 同步股票池可能消耗 Provider quota，因此必须要求登录用户触发。
    _ = current_user

    summary = await MarketSymbolSyncService(
        db,
        provider_name=provider,
    ).sync_symbol_pool(
        market=market,
        limit=limit,
    )

    return success_response(
        data={
            "status": summary.status,
            "provider": summary.provider,
            "market": summary.market,
            "fetched_count": summary.fetched_count,
            "source_inserted": summary.source_inserted,
            "source_updated": summary.source_updated,
            "source_skipped": summary.source_skipped,
            "canonical_inserted": summary.canonical_inserted,
            "canonical_updated": summary.canonical_updated,
            "canonical_skipped": summary.canonical_skipped,
            "error_message": summary.error_message,
        }
    )


@router.post(
    "/symbols/{symbol}",
    summary="Sync Market Symbol",
    response_model=ApiResponse[dict[str, object]],
)
async def sync_market_symbol(
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
):
    # current_user is intentionally required because provider calls may have cost.
    _ = current_user

    market_symbol = await MarketDataSyncService(db).sync_symbol(
        symbol=symbol,
        market=market,
    )

    return success_response(
        data={
            "id": market_symbol.id,
            "symbol": market_symbol.symbol,
            "market": market_symbol.market,
            "name": market_symbol.name,
            "source": market_symbol.source,
            "provider_symbol": market_symbol.provider_symbol,
            "synced": True,
        }
    )


@router.post(
    "/stocks/{symbol}/candles",
    summary="Sync Stock Candles",
    response_model=ApiResponse[dict[str, object]],
)
async def sync_stock_candles(
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
        description="Candle timeframe: 1d, 1h, or 5m",
    ),
    limit: int = Query(
        default=30,
        ge=1,
        le=1000,
        description="Number of candles to sync",
    ),
    adjust_type: AdjustType = Query(
        default="none",
        description="Adjustment type: none, qfq, or hfq",
    ),
):
    _ = current_user

    candles = await MarketDataSyncService(db).sync_candles(
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        limit=limit,
        adjust_type=adjust_type,
    )

    return success_response(
        data={
            "symbol": symbol.strip().upper(),
            "market": market,
            "timeframe": timeframe,
            "adjust_type": adjust_type,
            "synced_count": len(candles),
            "first_candle_time": candles[0].candle_time if candles else None,
            "last_candle_time": candles[-1].candle_time if candles else None,
            "source": candles[0].source if candles else None,
            "synced": True,
        }
    )
