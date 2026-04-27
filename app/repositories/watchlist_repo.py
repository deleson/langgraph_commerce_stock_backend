from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.watchlist_item import WatchlistItem


class WatchlistRepository:
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