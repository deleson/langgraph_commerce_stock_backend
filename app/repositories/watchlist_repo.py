"""自选股 Repository。

本文件封装 watchlist_items 表的数据访问。自选股属于用户私有资源，
所有详情查询、更新和删除都必须带 user_id，避免跨用户读取。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.watchlist_item import WatchlistItem


class WatchlistRepository:
    """同步自选股数据访问对象。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_user_id(self, user_id: int) -> list[WatchlistItem]:
        stmt = (
            select(WatchlistItem)
            .where(WatchlistItem.user_id == user_id)
            .order_by(WatchlistItem.created_at.desc())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_by_id_for_user(self, *, item_id: int, user_id: int) -> WatchlistItem | None:
        """按资源 id 和当前用户 id 查询自选股。

        不能只按 item_id 查询，否则用户可能通过猜测 id 访问别人的自选股。
        """

        stmt = select(WatchlistItem).where(
            WatchlistItem.id == item_id,
            WatchlistItem.user_id == user_id,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_symbol_market_for_user(
        self,
        *,
        user_id: int,
        symbol: str,
        market: str,
    ) -> WatchlistItem | None:
        stmt = select(WatchlistItem).where(
            WatchlistItem.user_id == user_id,
            WatchlistItem.symbol == symbol,
            WatchlistItem.market == market,
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def create(
        self,
        *,
        user_id: int,
        symbol: str,
        market: str,
        name: str | None = None,
        notes: str | None = None,
        alert_enabled: bool = False,
    ) -> WatchlistItem:
        item = WatchlistItem(
            user_id=user_id,
            symbol=symbol,
            market=market,
            name=name,
            notes=notes,
            alert_enabled=alert_enabled,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def save(self, item: WatchlistItem) -> WatchlistItem:
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete(self, item: WatchlistItem) -> None:
        self.db.delete(item)
        self.db.commit()


class AsyncWatchlistRepository:
    """异步自选股数据访问对象。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_user_id(self, user_id: int) -> list[WatchlistItem]:
        stmt = (
            select(WatchlistItem)
            .where(WatchlistItem.user_id == user_id)
            .order_by(WatchlistItem.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_ids_for_user(
        self,
        *,
        user_id: int,
        item_ids: list[int],
    ) -> list[WatchlistItem]:
        """批量读取当前用户选中的自选股，供纸面账户创建固定组合快照。"""

        if not item_ids:
            return []

        stmt = (
            select(WatchlistItem)
            .where(
                WatchlistItem.user_id == user_id,
                WatchlistItem.id.in_(item_ids),
            )
            .order_by(WatchlistItem.id.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_distinct_symbols(
        self,
        *,
        market: str | None = None,
        limit: int | None = None,
    ) -> list[tuple[str, str]]:
        """读取所有自选股中去重后的 market + symbol。

        K 线批量同步只能面向用户关注过的股票池，不能从 market_symbols 全市场表
        扫描，否则会把低频维护任务放大成不可控的全市场同步。
        """

        stmt = select(
            WatchlistItem.market,
            WatchlistItem.symbol,
        ).distinct()

        if market is not None:
            stmt = stmt.where(WatchlistItem.market == market)

        stmt = stmt.order_by(WatchlistItem.market.asc(), WatchlistItem.symbol.asc())

        if limit is not None:
            stmt = stmt.limit(limit)

        result = await self.db.execute(stmt)
        return [
            (row.market, row.symbol)
            for row in result.all()
        ]

    async def get_by_id_for_user(
        self,
        *,
        item_id: int,
        user_id: int,
    ) -> WatchlistItem | None:
        """按资源 id 和当前用户 id 查询自选股。"""

        stmt = select(WatchlistItem).where(
            WatchlistItem.id == item_id,
            WatchlistItem.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_symbol_market_for_user(
        self,
        *,
        user_id: int,
        symbol: str,
        market: str,
    ) -> WatchlistItem | None:
        stmt = select(WatchlistItem).where(
            WatchlistItem.user_id == user_id,
            WatchlistItem.symbol == symbol,
            WatchlistItem.market == market,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: int,
        symbol: str,
        market: str,
        name: str | None = None,
        notes: str | None = None,
        alert_enabled: bool = False,
    ) -> WatchlistItem:
        item = WatchlistItem(
            user_id=user_id,
            symbol=symbol,
            market=market,
            name=name,
            notes=notes,
            alert_enabled=alert_enabled,
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def save(self, item: WatchlistItem) -> WatchlistItem:
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def delete(self, item: WatchlistItem) -> None:
        await self.db.delete(item)
        await self.db.commit()
