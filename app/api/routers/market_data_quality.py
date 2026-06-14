"""行情数据质量 API Router。

该 Router 提供 K 线数据质量报告、同步状态和同步日志查询。
数据质量用于提示数据为空、不足、过旧等风险，避免量化和 AI 链路误用不可靠数据。
"""

from fastapi import APIRouter, Path, Query

from app.api.deps import AsyncCurrentUser, AsyncDBSession
from app.repositories.market_data_sync_repo import AsyncMarketDataSyncRepository
from app.schemas.common import ApiResponse
from app.schemas.market_data import AdjustType, CandleTimeframe, MarketCode, MarketDataSource
from app.schemas.market_data_sync import (
    MarketDataQualityReport,
    MarketDataSyncLogQuery,
    MarketDataSyncLogResponse,
    MarketDataSyncLogStatus,
    MarketDataSyncStatusQuery,
    MarketDataSyncStatusResponse,
    MarketDataSyncStatusValue,
)
from app.services.market_data_quality_report_service import MarketDataQualityReportService
from app.utils.responses import success_response


router = APIRouter(prefix="/market-data-quality", tags=["market-data-quality"])


@router.get(
    "/stocks/{symbol}/report",
    summary="Get Market Data Quality Report",
    response_model=ApiResponse[MarketDataQualityReport],
)
async def get_market_data_quality_report(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    symbol: str = Path(
        min_length=1,
        max_length=20,
        description="Stock symbol, for example 600519, AAPL, or 0700",
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
        default=120,
        ge=1,
        le=1000,
        description="Number of candles to inspect",
    ),
    adjust_type: AdjustType = Query(
        default="none",
        description="Adjustment type: none, qfq, or hfq",
    ),
    source: MarketDataSource | None = Query(
        default=None,
        description="Optional market data source filter",
    ),
    min_required: int = Query(
        default=1,
        ge=1,
        le=1000,
        description="Minimum candles required to consider data enough",
    ),
    stale_after_days: int | None = Query(
        default=None,
        ge=1,
        le=3650,
        description="Mark data as stale if latest candle is older than this many days",
    ),
):
    _ = current_user

    report = await MarketDataQualityReportService(db).get_quality_report(
        symbol=symbol,
        market=market,
        timeframe=timeframe,
        limit=limit,
        adjust_type=adjust_type,
        source=source,
        min_required=min_required,
        stale_after_days=stale_after_days,
    )

    return success_response(data=report)


@router.get(
    "/sync-statuses",
    summary="List Market Data Sync Statuses",
    response_model=ApiResponse[list[MarketDataSyncStatusResponse]],
)
async def list_market_data_sync_statuses(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    symbol: str | None = Query(
        default=None,
        min_length=1,
        max_length=20,
        description="Optional stock symbol filter",
    ),
    market: MarketCode | None = Query(
        default=None,
        description="Optional market code filter",
    ),
    timeframe: CandleTimeframe | None = Query(
        default=None,
        description="Optional candle timeframe filter",
    ),
    source: MarketDataSource | None = Query(
        default=None,
        description="Optional source filter",
    ),
    adjust_type: AdjustType | None = Query(
        default=None,
        description="Optional adjustment type filter",
    ),
    status: MarketDataSyncStatusValue | None = Query(
        default=None,
        description="Optional sync status filter",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of records",
    ),
):
    _ = current_user

    statuses = await AsyncMarketDataSyncRepository(db).list_statuses(
        MarketDataSyncStatusQuery(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            source=source,
            adjust_type=adjust_type,
            status=status,
            limit=limit,
        )
    )

    return success_response(
        data=[
            MarketDataSyncStatusResponse.model_validate(status_item)
            for status_item in statuses
        ]
    )


@router.get(
    "/sync-logs",
    summary="List Market Data Sync Logs",
    response_model=ApiResponse[list[MarketDataSyncLogResponse]],
)
async def list_market_data_sync_logs(
    current_user: AsyncCurrentUser,
    db: AsyncDBSession,
    symbol: str | None = Query(
        default=None,
        min_length=1,
        max_length=20,
        description="Optional stock symbol filter",
    ),
    market: MarketCode | None = Query(
        default=None,
        description="Optional market code filter",
    ),
    timeframe: CandleTimeframe | None = Query(
        default=None,
        description="Optional candle timeframe filter",
    ),
    source: MarketDataSource | None = Query(
        default=None,
        description="Optional source filter",
    ),
    adjust_type: AdjustType | None = Query(
        default=None,
        description="Optional adjustment type filter",
    ),
    status: MarketDataSyncLogStatus | None = Query(
        default=None,
        description="Optional log status filter",
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="Maximum number of records",
    ),
):
    _ = current_user

    logs = await AsyncMarketDataSyncRepository(db).list_logs(
        MarketDataSyncLogQuery(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            source=source,
            adjust_type=adjust_type,
            status=status,
            limit=limit,
        )
    )

    return success_response(
        data=[
            MarketDataSyncLogResponse.model_validate(log_item)
            for log_item in logs
        ]
    )
