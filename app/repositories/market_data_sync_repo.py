"""行情同步 Repository。

本文件封装行情同步状态和同步日志的数据访问。状态表记录某个股票当前最新同步结果，
日志表记录每一次同步过程，二者一起支撑生产排查和数据质量追踪。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_sync_log import MarketDataSyncLog
from app.models.market_data_sync_status import MarketDataSyncStatus
from app.schemas.market_data_sync import (
    MarketDataSyncLogCreate,
    MarketDataSyncLogQuery,
    MarketDataSyncLogUpdate,
    MarketDataSyncStatusCreate,
    MarketDataSyncStatusQuery,
    MarketDataSyncStatusUpdate,
)


class AsyncMarketDataSyncRepository:
    """异步行情同步数据访问对象。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_status(
        self,
        *,
        symbol: str,
        market: str,
        timeframe: str,
        source: str,
        adjust_type: str,
    ) -> MarketDataSyncStatus | None:
        stmt = select(MarketDataSyncStatus).where(
            MarketDataSyncStatus.symbol == symbol,
            MarketDataSyncStatus.market == market,
            MarketDataSyncStatus.timeframe == timeframe,
            MarketDataSyncStatus.source == source,
            MarketDataSyncStatus.adjust_type == adjust_type,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_statuses(
        self,
        query: MarketDataSyncStatusQuery,
    ) -> list[MarketDataSyncStatus]:
        stmt = select(MarketDataSyncStatus)

        if query.symbol is not None:
            stmt = stmt.where(MarketDataSyncStatus.symbol == query.symbol)

        if query.market is not None:
            stmt = stmt.where(MarketDataSyncStatus.market == query.market)

        if query.timeframe is not None:
            stmt = stmt.where(MarketDataSyncStatus.timeframe == query.timeframe)

        if query.source is not None:
            stmt = stmt.where(MarketDataSyncStatus.source == query.source)

        if query.adjust_type is not None:
            stmt = stmt.where(MarketDataSyncStatus.adjust_type == query.adjust_type)

        if query.status is not None:
            stmt = stmt.where(MarketDataSyncStatus.status == query.status)

        stmt = stmt.order_by(MarketDataSyncStatus.updated_at.desc()).limit(query.limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create_status(
        self,
        payload: MarketDataSyncStatusCreate,
    ) -> MarketDataSyncStatus:
        status = MarketDataSyncStatus(**payload.model_dump())
        self.db.add(status)
        await self.db.commit()
        await self.db.refresh(status)
        return status

    async def update_status(
        self,
        status: MarketDataSyncStatus,
        payload: MarketDataSyncStatusUpdate,
    ) -> MarketDataSyncStatus:
        update_data = payload.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(status, field, value)

        self.db.add(status)
        await self.db.commit()
        await self.db.refresh(status)
        return status

    async def upsert_status(
        self,
        payload: MarketDataSyncStatusCreate,
    ) -> MarketDataSyncStatus:
        """创建或更新某个行情维度的同步状态。

        symbol、market、timeframe、source、adjust_type 共同决定一条状态记录。
        """

        existing = await self.get_status(
            symbol=payload.symbol,
            market=payload.market,
            timeframe=payload.timeframe,
            source=payload.source,
            adjust_type=payload.adjust_type,
        )

        if existing is None:
            return await self.create_status(payload)

        update_payload = MarketDataSyncStatusUpdate(
            status=payload.status,
            last_success_at=payload.last_success_at,
            last_failed_at=payload.last_failed_at,
            earliest_candle_time=payload.earliest_candle_time,
            latest_candle_time=payload.latest_candle_time,
            candle_count=payload.candle_count,
            last_error_message=payload.last_error_message,
        )
        return await self.update_status(existing, update_payload)

    async def create_log(
        self,
        payload: MarketDataSyncLogCreate,
    ) -> MarketDataSyncLog:
        log = MarketDataSyncLog(**payload.model_dump())
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def update_log(
        self,
        log: MarketDataSyncLog,
        payload: MarketDataSyncLogUpdate,
    ) -> MarketDataSyncLog:
        update_data = payload.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(log, field, value)

        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def list_logs(
        self,
        query: MarketDataSyncLogQuery,
    ) -> list[MarketDataSyncLog]:
        stmt = select(MarketDataSyncLog)

        if query.symbol is not None:
            stmt = stmt.where(MarketDataSyncLog.symbol == query.symbol)

        if query.market is not None:
            stmt = stmt.where(MarketDataSyncLog.market == query.market)

        if query.timeframe is not None:
            stmt = stmt.where(MarketDataSyncLog.timeframe == query.timeframe)

        if query.source is not None:
            stmt = stmt.where(MarketDataSyncLog.source == query.source)

        if query.adjust_type is not None:
            stmt = stmt.where(MarketDataSyncLog.adjust_type == query.adjust_type)

        if query.status is not None:
            stmt = stmt.where(MarketDataSyncLog.status == query.status)

        stmt = stmt.order_by(MarketDataSyncLog.started_at.desc()).limit(query.limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_log(
        self,
        *,
        symbol: str,
        market: str,
        timeframe: str,
        source: str,
        adjust_type: str,
    ) -> MarketDataSyncLog | None:
        """查询某个行情维度最近一次同步日志。"""

        stmt = (
            select(MarketDataSyncLog)
            .where(
                MarketDataSyncLog.symbol == symbol,
                MarketDataSyncLog.market == market,
                MarketDataSyncLog.timeframe == timeframe,
                MarketDataSyncLog.source == source,
                MarketDataSyncLog.adjust_type == adjust_type,
            )
            .order_by(MarketDataSyncLog.started_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
