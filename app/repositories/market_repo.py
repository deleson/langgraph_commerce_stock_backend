from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_candle import MarketCandle
from app.models.market_symbol import MarketSymbol
from app.schemas.market_data import (
    MarketCandleCreate,
    MarketCandleQuery,
    MarketSymbolCreate,
    MarketSymbolUpdate,
)


class AsyncMarketRepository:
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
        symbol = MarketSymbol(**payload.model_dump())
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
            source=payload.source,
            is_active=payload.is_active,
        )
        return await self.update_symbol(existing, update_payload)

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