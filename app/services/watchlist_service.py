"""自选股 Service。

本文件负责当前用户自选股的创建、查询、更新和删除。
自选股是日报、量化提醒和纸面交易扫描股票池的重要来源，必须按 user_id 做隔离。
"""

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.models.user import User
from app.models.watchlist_item import WatchlistItem
from app.repositories.user_preference_repo import UserPreferenceRepository
from app.repositories.watchlist_repo import WatchlistRepository
from app.schemas.watchlist import WatchlistCreateRequest, WatchlistUpdateRequest
from app.repositories.watchlist_repo import AsyncWatchlistRepository
from app.repositories.user_preference_repo import AsyncUserPreferenceRepository


class WatchlistService:
    """同步自选股业务服务。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.watchlist_repo = WatchlistRepository(db)
        self.preference_repo = UserPreferenceRepository(db)

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return symbol.strip().upper()

    @staticmethod
    def _normalize_market(market: str) -> str:
        return market.strip().upper()

    def list_my_watchlist(self, user: User) -> list[WatchlistItem]:
        return self.watchlist_repo.list_by_user_id(user.id)

    def get_my_watchlist_item(self, *, user: User, item_id: int) -> WatchlistItem:
        """查询当前用户自选股详情。"""

        item = self.watchlist_repo.get_by_id_for_user(
            item_id=item_id,
            user_id=user.id,
        )
        if item is None:
            raise NotFoundException(
                message="watchlist item not found",
                details=[{"field": "item_id", "reason": "watchlist item does not exist"}],
            )

        return item

    def create_watchlist_item(
        self,
        *,
        user: User,
        payload: WatchlistCreateRequest,
    ) -> WatchlistItem:
        """创建当前用户自选股。

        同一用户不能重复添加同一市场同一股票；提醒默认值可继承用户偏好。
        """

        symbol = self._normalize_symbol(payload.symbol)
        market = self._normalize_market(payload.market)

        existing_item = self.watchlist_repo.get_by_symbol_market_for_user(
            user_id=user.id,
            symbol=symbol,
            market=market,
        )
        if existing_item is not None:
            raise ConflictException(
                message="watchlist item already exists",
                details=[
                    {
                        "field": "symbol",
                        "reason": "symbol already exists in current user's watchlist",
                    }
                ],
            )

        alert_enabled = payload.alert_enabled
        if alert_enabled is None:
            preference = self.preference_repo.get_by_user_id(user.id)
            alert_enabled = (
                preference.default_watchlist_alert_enabled
                if preference is not None
                else False
            )

        return self.watchlist_repo.create(
            user_id=user.id,
            symbol=symbol,
            market=market,
            name=payload.name,
            notes=payload.notes,
            alert_enabled=alert_enabled,
        )

    def update_watchlist_item(
        self,
        *,
        user: User,
        item_id: int,
        payload: WatchlistUpdateRequest,
    ) -> WatchlistItem:
        item = self.get_my_watchlist_item(user=user, item_id=item_id)

        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(item, field, value)

        return self.watchlist_repo.save(item)

    def delete_watchlist_item(self, *, user: User, item_id: int) -> None:
        item = self.get_my_watchlist_item(user=user, item_id=item_id)
        self.watchlist_repo.delete(item)



class AsyncWatchlistService:
    """异步自选股业务服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.watchlist_repo = AsyncWatchlistRepository(db)
        self.preference_repo = AsyncUserPreferenceRepository(db)

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return symbol.strip().upper()

    @staticmethod
    def _normalize_market(market: str) -> str:
        return market.strip().upper()

    async def list_my_watchlist(self, user: User) -> list[WatchlistItem]:
        return await self.watchlist_repo.list_by_user_id(user.id)

    async def get_my_watchlist_item(
        self,
        *,
        user: User,
        item_id: int,
    ) -> WatchlistItem:
        """查询当前用户自选股详情。"""

        item = await self.watchlist_repo.get_by_id_for_user(
            item_id=item_id,
            user_id=user.id,
        )
        if item is None:
            raise NotFoundException(
                message="watchlist item not found",
                details=[{"field": "item_id", "reason": "watchlist item does not exist"}],
            )

        return item

    async def create_watchlist_item(
        self,
        *,
        user: User,
        payload: WatchlistCreateRequest,
    ) -> WatchlistItem:
        """创建当前用户自选股。"""

        symbol = self._normalize_symbol(payload.symbol)
        market = self._normalize_market(payload.market)

        existing_item = await self.watchlist_repo.get_by_symbol_market_for_user(
            user_id=user.id,
            symbol=symbol,
            market=market,
        )
        if existing_item is not None:
            raise ConflictException(
                message="watchlist item already exists",
                details=[
                    {
                        "field": "symbol",
                        "reason": "symbol already exists in current user's watchlist",
                    }
                ],
            )

        alert_enabled = payload.alert_enabled
        if alert_enabled is None:
            preference = await self.preference_repo.get_by_user_id(user.id)
            alert_enabled = (
                preference.default_watchlist_alert_enabled
                if preference is not None
                else False
            )

        return await self.watchlist_repo.create(
            user_id=user.id,
            symbol=symbol,
            market=market,
            name=payload.name,
            notes=payload.notes,
            alert_enabled=alert_enabled,
        )

    async def update_watchlist_item(
        self,
        *,
        user: User,
        item_id: int,
        payload: WatchlistUpdateRequest,
    ) -> WatchlistItem:
        item = await self.get_my_watchlist_item(user=user, item_id=item_id)

        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(item, field, value)

        return await self.watchlist_repo.save(item)

    async def delete_watchlist_item(self, *, user: User, item_id: int) -> None:
        item = await self.get_my_watchlist_item(user=user, item_id=item_id)
        await self.watchlist_repo.delete(item)
