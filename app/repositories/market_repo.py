"""行情 Repository。

本文件封装 market_symbols 和 market_candles 的数据访问。K 线查询必须区分
market、symbol、timeframe、source 和 adjust_type，否则技术指标、回测和策略信号会混用数据。
"""

from collections.abc import Sequence

from datetime import UTC, datetime

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_candle import MarketCandle
from app.models.market_symbol import MarketSymbol
from app.models.market_symbol_source import MarketSymbolSource
from app.schemas.market_data import (
    MarketCandleCreate,
    MarketCandleQuery,
    MarketSymbolCreate,
    MarketSymbolSourceCreate,
    MarketSymbolUpdate,
)


class AsyncMarketRepository:
    """异步行情数据访问对象。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_symbol(
        self,
        *,
        symbol: str,
        market: str,
    ) -> MarketSymbol | None:
        stmt = select(MarketSymbol).where(
            MarketSymbol.symbol == symbol,
            MarketSymbol.market == market,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_symbols(
        self,
        *,
        market: str | None = None,
        keyword: str | None = None,
        active_only: bool = True,
        limit: int = 50,
    ) -> list[MarketSymbol]:
        stmt = select(MarketSymbol)

        if market is not None:
            stmt = stmt.where(MarketSymbol.market == market)

        if active_only:
            stmt = stmt.where(MarketSymbol.is_active.is_(True))

        if keyword:
            normalized_keyword = keyword.strip().upper()
            stmt = stmt.where(
                MarketSymbol.symbol.ilike(f"%{normalized_keyword}%")
                | MarketSymbol.name.ilike(f"%{keyword.strip()}%")
            )

        stmt = stmt.order_by(MarketSymbol.market.asc(), MarketSymbol.symbol.asc()).limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create_symbol(
        self,
        payload: MarketSymbolCreate,
    ) -> MarketSymbol:
        symbol = MarketSymbol(**self._symbol_model_data(payload))
        self.db.add(symbol)
        await self.db.commit()
        await self.db.refresh(symbol)
        return symbol

    async def update_symbol(
        self,
        symbol: MarketSymbol,
        payload: MarketSymbolUpdate,
    ) -> MarketSymbol:
        update_data = payload.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(symbol, field, value)

        self.db.add(symbol)
        await self.db.commit()
        await self.db.refresh(symbol)
        return symbol

    async def upsert_symbol(
        self,
        payload: MarketSymbolCreate,
    ) -> MarketSymbol:
        """按 market + symbol 创建或更新股票基础信息。"""

        existing = await self.get_symbol(
            symbol=payload.symbol,
            market=payload.market,
        )

        if existing is None:
            return await self.create_symbol(payload)

        update_payload = MarketSymbolUpdate(
            name=payload.name,
            currency=payload.currency,
            exchange=payload.exchange,
            provider_symbol=payload.provider_symbol,
            list_status=payload.list_status,
            source=payload.source,
            is_active=payload.is_active,
            data_hash=payload.data_hash,
            last_synced_at=payload.last_synced_at,
            sync_status=payload.sync_status,
            last_sync_error=payload.last_sync_error,
        )
        return await self.update_symbol(existing, update_payload)

    async def upsert_symbols_bulk(
        self,
        payloads: Sequence[MarketSymbolCreate],
    ) -> dict[str, int]:
        """批量 upsert 统一股票基础信息。

        全量股票池同步不能逐条 SELECT/UPDATE/COMMIT。这里先一次性取出已有记录，
        在内存里按 market + symbol 对比哈希，只有变化的数据才写库。
        """

        if not payloads:
            return {
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
            }

        keys = {(payload.market, payload.symbol) for payload in payloads}
        existing_symbols = await self.list_symbols_by_keys(keys)
        existing_map = {
            (symbol.market, symbol.symbol): symbol
            for symbol in existing_symbols
        }

        inserted = 0
        updated = 0
        skipped = 0

        for payload in payloads:
            key = (payload.market, payload.symbol)
            existing = existing_map.get(key)
            model_data = self._symbol_model_data(payload)

            if existing is None:
                self.db.add(MarketSymbol(**model_data))
                inserted += 1
                continue

            if payload.data_hash and existing.data_hash == payload.data_hash:
                skipped += 1
                continue

            for field, value in model_data.items():
                setattr(existing, field, value)
            self.db.add(existing)
            updated += 1

        await self.db.commit()

        return {
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
        }

    async def list_symbols_by_keys(
        self,
        keys: set[tuple[str, str]],
    ) -> list[MarketSymbol]:
        if not keys:
            return []

        stmt = select(MarketSymbol).where(
            tuple_(MarketSymbol.market, MarketSymbol.symbol).in_(keys)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_symbol_source(
        self,
        *,
        provider: str,
        market: str,
        symbol: str,
    ) -> MarketSymbolSource | None:
        stmt = select(MarketSymbolSource).where(
            MarketSymbolSource.provider == provider,
            MarketSymbolSource.market == market,
            MarketSymbolSource.symbol == symbol,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_symbol_sources_by_keys(
        self,
        keys: set[tuple[str, str, str]],
    ) -> list[MarketSymbolSource]:
        if not keys:
            return []

        stmt = select(MarketSymbolSource).where(
            tuple_(
                MarketSymbolSource.provider,
                MarketSymbolSource.market,
                MarketSymbolSource.symbol,
            ).in_(keys)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def upsert_symbol_sources_bulk(
        self,
        payloads: Sequence[MarketSymbolSourceCreate],
    ) -> dict[str, int]:
        """批量 upsert Provider 来源记录，并用哈希跳过未变化记录。"""

        if not payloads:
            return {
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
            }

        keys = {
            (payload.provider, payload.market, payload.symbol)
            for payload in payloads
        }
        existing_sources = await self.list_symbol_sources_by_keys(keys)
        existing_map = {
            (source.provider, source.market, source.symbol): source
            for source in existing_sources
        }

        inserted = 0
        updated = 0
        skipped = 0

        for payload in payloads:
            key = (payload.provider, payload.market, payload.symbol)
            existing = existing_map.get(key)
            model_data = payload.model_dump()

            if existing is None:
                self.db.add(MarketSymbolSource(**model_data))
                inserted += 1
                continue

            if (
                existing.raw_hash == payload.raw_hash
                and existing.normalized_hash == payload.normalized_hash
            ):
                skipped += 1
                continue

            for field, value in model_data.items():
                setattr(existing, field, value)
            self.db.add(existing)
            updated += 1

        await self.db.commit()

        return {
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
        }

    def _symbol_model_data(
        self,
        payload: MarketSymbolCreate,
    ) -> dict:
        data = payload.model_dump(
            exclude={
                "raw_payload",
            }
        )
        if data.get("last_synced_at") is None and data.get("sync_status") == "success":
            data["last_synced_at"] = datetime.now(UTC)
        return data

    async def get_candle(
        self,
        *,
        symbol: str,
        market: str,
        timeframe: str,
        candle_time,
        source: str,
        adjust_type: str,
    ) -> MarketCandle | None:
        stmt = select(MarketCandle).where(
            MarketCandle.symbol == symbol,
            MarketCandle.market == market,
            MarketCandle.timeframe == timeframe,
            MarketCandle.candle_time == candle_time,
            MarketCandle.source == source,
            MarketCandle.adjust_type == adjust_type,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_candles(
        self,
        query: MarketCandleQuery,
    ) -> list[MarketCandle]:
        """按查询条件读取最近 K 线，并按时间升序返回。

        数据库先倒序取最近 N 条，再反转为升序，方便指标计算和回测按时间推进。
        """

        stmt = select(MarketCandle).where(
            MarketCandle.symbol == query.symbol,
            MarketCandle.market == query.market,
            MarketCandle.timeframe == query.timeframe,
            MarketCandle.adjust_type == query.adjust_type,
        )

        if query.source is not None:
            stmt = stmt.where(MarketCandle.source == query.source)

        stmt = stmt.order_by(MarketCandle.candle_time.desc()).limit(query.limit)

        result = await self.db.execute(stmt)
        candles = list(result.scalars().all())

        return list(reversed(candles))

    async def list_candles_by_date_range(
        self,
        *,
        symbol: str,
        market: str,
        timeframe: str,
        start_at,
        end_at,
        adjust_type: str = "none",
        source: str | None = None,
    ) -> list[MarketCandle]:
        stmt = select(MarketCandle).where(
            MarketCandle.symbol == symbol,
            MarketCandle.market == market,
            MarketCandle.timeframe == timeframe,
            MarketCandle.adjust_type == adjust_type,
            MarketCandle.candle_time >= start_at,
            MarketCandle.candle_time <= end_at,
        )

        if source is not None:
            stmt = stmt.where(MarketCandle.source == source)

        stmt = stmt.order_by(MarketCandle.candle_time.asc())

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create_candle(
        self,
        payload: MarketCandleCreate,
    ) -> MarketCandle:
        candle = MarketCandle(**payload.model_dump())
        self.db.add(candle)
        await self.db.commit()
        await self.db.refresh(candle)
        return candle

    async def upsert_candle(
        self,
        payload: MarketCandleCreate,
    ) -> MarketCandle:
        """按唯一业务键创建或更新单根 K 线。

        唯一键包含 source 和 adjust_type，避免不同数据源或复权口径互相覆盖。
        """

        existing = await self.get_candle(
            symbol=payload.symbol,
            market=payload.market,
            timeframe=payload.timeframe,
            candle_time=payload.candle_time,
            source=payload.source,
            adjust_type=payload.adjust_type,
        )

        if existing is None:
            return await self.create_candle(payload)

        update_data = payload.model_dump(exclude={"symbol", "market", "timeframe", "candle_time", "source", "adjust_type"})

        for field, value in update_data.items():
            setattr(existing, field, value)

        self.db.add(existing)
        await self.db.commit()
        await self.db.refresh(existing)
        return existing

    async def upsert_candles(
        self,
        payloads: Sequence[MarketCandleCreate],
    ) -> list[MarketCandle]:
        candles: list[MarketCandle] = []

        for payload in payloads:
            candle = await self.upsert_candle(payload)
            candles.append(candle)

        return candles
