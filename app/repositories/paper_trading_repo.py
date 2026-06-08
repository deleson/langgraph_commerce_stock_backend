from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper_trading_account import PaperTradingAccount
from app.models.paper_trading_equity_snapshot import PaperTradingEquitySnapshot
from app.models.paper_trading_order import PaperTradingOrder
from app.models.paper_trading_position import PaperTradingPosition
from app.models.paper_trading_trade import PaperTradingTrade
from app.schemas.paper_trading import (
    PaperTradingAccountCreate,
    PaperTradingAccountStatus,
    PaperTradingAccountUpdate,
    PaperTradingListQuery,
    PaperTradingOrderCreate,
    PaperTradingOrderStatus,
)


class AsyncPaperTradingRepository:
    """Database access for paper trading accounts, positions, orders, trades, and equity snapshots.

    Repository only reads and writes database rows.
    It does not decide whether a strategy should buy or sell.
    It does not calculate signals, holdings, cash, or returns.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_account(
        self,
        *,
        user_id: int,
        payload: PaperTradingAccountCreate,
    ) -> PaperTradingAccount:
        account = PaperTradingAccount(
            user_id=user_id,
            name=payload.name,
            initial_cash=payload.initial_cash,
            cash_balance=payload.initial_cash,
            currency=payload.currency,
            status=PaperTradingAccountStatus.ACTIVE,
        )

        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return account

    async def get_account(
        self,
        *,
        account_id: int,
        user_id: int,
    ) -> PaperTradingAccount | None:
        stmt = select(PaperTradingAccount).where(
            PaperTradingAccount.id == account_id,
            PaperTradingAccount.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_accounts(
        self,
        *,
        user_id: int,
        query: PaperTradingListQuery,
    ) -> list[PaperTradingAccount]:
        stmt = (
            select(PaperTradingAccount)
            .where(PaperTradingAccount.user_id == user_id)
            .order_by(PaperTradingAccount.created_at.desc())
            .offset(query.offset)
            .limit(query.limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_accounts(
        self,
        *,
        user_id: int,
    ) -> int:
        stmt = select(func.count(PaperTradingAccount.id)).where(
            PaperTradingAccount.user_id == user_id
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def list_active_accounts(
        self,
        *,
        limit: int = 500,
        offset: int = 0,
    ) -> list[PaperTradingAccount]:
        stmt = (
            select(PaperTradingAccount)
            .where(PaperTradingAccount.status == PaperTradingAccountStatus.ACTIVE)
            .order_by(PaperTradingAccount.id.asc())
            .offset(offset)
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_account(
        self,
        account: PaperTradingAccount,
        payload: PaperTradingAccountUpdate,
    ) -> PaperTradingAccount:
        update_data = payload.model_dump(
            mode="json",
            exclude_unset=True,
        )

        for field, value in update_data.items():
            setattr(account, field, value)

        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return account

    async def update_account_cash(
        self,
        *,
        account: PaperTradingAccount,
        cash_balance: Decimal,
    ) -> PaperTradingAccount:
        account.cash_balance = cash_balance

        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return account

    async def get_position(
        self,
        *,
        account_id: int,
        symbol: str,
        market: str,
    ) -> PaperTradingPosition | None:
        stmt = select(PaperTradingPosition).where(
            PaperTradingPosition.account_id == account_id,
            PaperTradingPosition.symbol == symbol,
            PaperTradingPosition.market == market,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_positions(
        self,
        *,
        account_id: int,
        user_id: int,
        query: PaperTradingListQuery,
    ) -> list[PaperTradingPosition]:
        stmt = (
            select(PaperTradingPosition)
            .join(
                PaperTradingAccount,
                PaperTradingPosition.account_id == PaperTradingAccount.id,
            )
            .where(
                PaperTradingPosition.account_id == account_id,
                PaperTradingAccount.user_id == user_id,
            )
            .order_by(PaperTradingPosition.updated_at.desc())
            .offset(query.offset)
            .limit(query.limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_positions(
        self,
        *,
        account_id: int,
        user_id: int,
    ) -> int:
        stmt = (
            select(func.count(PaperTradingPosition.id))
            .join(
                PaperTradingAccount,
                PaperTradingPosition.account_id == PaperTradingAccount.id,
            )
            .where(
                PaperTradingPosition.account_id == account_id,
                PaperTradingAccount.user_id == user_id,
            )
        )

        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def create_position(
        self,
        *,
        account_id: int,
        symbol: str,
        market: str,
        quantity: Decimal,
        avg_cost: Decimal,
        last_price: Decimal | None,
        market_value: Decimal,
        unrealized_pnl: Decimal,
        unrealized_return: Decimal | None,
    ) -> PaperTradingPosition:
        position = PaperTradingPosition(
            account_id=account_id,
            symbol=symbol,
            market=market,
            quantity=quantity,
            avg_cost=avg_cost,
            last_price=last_price,
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
            unrealized_return=unrealized_return,
        )

        self.db.add(position)
        await self.db.commit()
        await self.db.refresh(position)
        return position

    async def update_position(
        self,
        *,
        position: PaperTradingPosition,
        quantity: Decimal,
        avg_cost: Decimal,
        last_price: Decimal | None,
        market_value: Decimal,
        unrealized_pnl: Decimal,
        unrealized_return: Decimal | None,
    ) -> PaperTradingPosition:
        position.quantity = quantity
        position.avg_cost = avg_cost
        position.last_price = last_price
        position.market_value = market_value
        position.unrealized_pnl = unrealized_pnl
        position.unrealized_return = unrealized_return

        self.db.add(position)
        await self.db.commit()
        await self.db.refresh(position)
        return position

    async def create_order(
        self,
        payload: PaperTradingOrderCreate,
    ) -> PaperTradingOrder:
        order = PaperTradingOrder(
            account_id=payload.account_id,
            symbol=payload.symbol,
            market=payload.market,
            side=payload.side,
            status=PaperTradingOrderStatus.PENDING,
            planned_quantity=payload.planned_quantity,
            planned_price=payload.planned_price,
            filled_quantity=Decimal("0"),
            filled_price=None,
            signal_source=payload.signal_source,
            signal_snapshot=payload.signal_snapshot,
            reason=payload.reason,
        )

        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def get_order(
        self,
        *,
        order_id: int,
        account_id: int,
        user_id: int,
    ) -> PaperTradingOrder | None:
        stmt = (
            select(PaperTradingOrder)
            .join(
                PaperTradingAccount,
                PaperTradingOrder.account_id == PaperTradingAccount.id,
            )
            .where(
                PaperTradingOrder.id == order_id,
                PaperTradingOrder.account_id == account_id,
                PaperTradingAccount.user_id == user_id,
            )
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_orders(
        self,
        *,
        account_id: int,
        user_id: int,
        query: PaperTradingListQuery,
    ) -> list[PaperTradingOrder]:
        stmt = (
            select(PaperTradingOrder)
            .join(
                PaperTradingAccount,
                PaperTradingOrder.account_id == PaperTradingAccount.id,
            )
            .where(
                PaperTradingOrder.account_id == account_id,
                PaperTradingAccount.user_id == user_id,
            )
            .order_by(PaperTradingOrder.created_at.desc())
            .offset(query.offset)
            .limit(query.limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_orders(
        self,
        *,
        account_id: int,
        user_id: int,
    ) -> int:
        stmt = (
            select(func.count(PaperTradingOrder.id))
            .join(
                PaperTradingAccount,
                PaperTradingOrder.account_id == PaperTradingAccount.id,
            )
            .where(
                PaperTradingOrder.account_id == account_id,
                PaperTradingAccount.user_id == user_id,
            )
        )

        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def mark_order_filled(
        self,
        *,
        order: PaperTradingOrder,
        filled_quantity: Decimal,
        filled_price: Decimal,
    ) -> PaperTradingOrder:
        order.status = PaperTradingOrderStatus.FILLED
        order.filled_quantity = filled_quantity
        order.filled_price = filled_price

        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def update_order_status(
        self,
        *,
        order: PaperTradingOrder,
        status: PaperTradingOrderStatus,
    ) -> PaperTradingOrder:
        order.status = status

        self.db.add(order)
        await self.db.commit()
        await self.db.refresh(order)
        return order

    async def create_trade(
        self,
        *,
        account_id: int,
        order_id: int | None,
        symbol: str,
        market: str,
        side: str,
        filled_quantity: Decimal,
        filled_price: Decimal,
        trade_value: Decimal,
        fee_amount: Decimal,
        traded_at: datetime,
    ) -> PaperTradingTrade:
        trade = PaperTradingTrade(
            account_id=account_id,
            order_id=order_id,
            symbol=symbol,
            market=market,
            side=side,
            filled_quantity=filled_quantity,
            filled_price=filled_price,
            trade_value=trade_value,
            fee_amount=fee_amount,
            traded_at=traded_at,
        )

        self.db.add(trade)
        await self.db.commit()
        await self.db.refresh(trade)
        return trade

    async def list_trades(
        self,
        *,
        account_id: int,
        user_id: int,
        query: PaperTradingListQuery,
    ) -> list[PaperTradingTrade]:
        stmt = (
            select(PaperTradingTrade)
            .join(
                PaperTradingAccount,
                PaperTradingTrade.account_id == PaperTradingAccount.id,
            )
            .where(
                PaperTradingTrade.account_id == account_id,
                PaperTradingAccount.user_id == user_id,
            )
            .order_by(PaperTradingTrade.traded_at.desc())
            .offset(query.offset)
            .limit(query.limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_trades(
        self,
        *,
        account_id: int,
        user_id: int,
    ) -> int:
        stmt = (
            select(func.count(PaperTradingTrade.id))
            .join(
                PaperTradingAccount,
                PaperTradingTrade.account_id == PaperTradingAccount.id,
            )
            .where(
                PaperTradingTrade.account_id == account_id,
                PaperTradingAccount.user_id == user_id,
            )
        )

        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def create_equity_snapshot(
        self,
        *,
        account_id: int,
        snapshot_date: date,
        cash_balance: Decimal,
        position_market_value: Decimal,
        total_equity: Decimal,
        total_return: Decimal,
        daily_return: Decimal | None,
        max_drawdown: Decimal | None,
    ) -> PaperTradingEquitySnapshot:
        snapshot = PaperTradingEquitySnapshot(
            account_id=account_id,
            snapshot_date=snapshot_date,
            cash_balance=cash_balance,
            position_market_value=position_market_value,
            total_equity=total_equity,
            total_return=total_return,
            daily_return=daily_return,
            max_drawdown=max_drawdown,
        )

        self.db.add(snapshot)
        await self.db.commit()
        await self.db.refresh(snapshot)
        return snapshot

    async def get_equity_snapshot_by_date(
        self,
        *,
        account_id: int,
        snapshot_date: date,
    ) -> PaperTradingEquitySnapshot | None:
        stmt = select(PaperTradingEquitySnapshot).where(
            PaperTradingEquitySnapshot.account_id == account_id,
            PaperTradingEquitySnapshot.snapshot_date == snapshot_date,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_equity_snapshot(
        self,
        *,
        account_id: int,
        user_id: int,
    ) -> PaperTradingEquitySnapshot | None:
        stmt = (
            select(PaperTradingEquitySnapshot)
            .join(
                PaperTradingAccount,
                PaperTradingEquitySnapshot.account_id == PaperTradingAccount.id,
            )
            .where(
                PaperTradingEquitySnapshot.account_id == account_id,
                PaperTradingAccount.user_id == user_id,
            )
            .order_by(PaperTradingEquitySnapshot.snapshot_date.desc())
            .limit(1)
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_equity_snapshots(
        self,
        *,
        account_id: int,
        user_id: int,
        query: PaperTradingListQuery,
    ) -> list[PaperTradingEquitySnapshot]:
        stmt = (
            select(PaperTradingEquitySnapshot)
            .join(
                PaperTradingAccount,
                PaperTradingEquitySnapshot.account_id == PaperTradingAccount.id,
            )
            .where(
                PaperTradingEquitySnapshot.account_id == account_id,
                PaperTradingAccount.user_id == user_id,
            )
            .order_by(PaperTradingEquitySnapshot.snapshot_date.desc())
            .offset(query.offset)
            .limit(query.limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_equity_snapshots(
        self,
        *,
        account_id: int,
        user_id: int,
    ) -> int:
        stmt = (
            select(func.count(PaperTradingEquitySnapshot.id))
            .join(
                PaperTradingAccount,
                PaperTradingEquitySnapshot.account_id == PaperTradingAccount.id,
            )
            .where(
                PaperTradingEquitySnapshot.account_id == account_id,
                PaperTradingAccount.user_id == user_id,
            )
        )

        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def update_equity_snapshot(
        self,
        *,
        snapshot: PaperTradingEquitySnapshot,
        cash_balance: Decimal,
        position_market_value: Decimal,
        total_equity: Decimal,
        total_return: Decimal,
        daily_return: Decimal | None,
        max_drawdown: Decimal | None,
    ) -> PaperTradingEquitySnapshot:
        snapshot.cash_balance = cash_balance
        snapshot.position_market_value = position_market_value
        snapshot.total_equity = total_equity
        snapshot.total_return = total_return
        snapshot.daily_return = daily_return
        snapshot.max_drawdown = max_drawdown

        self.db.add(snapshot)
        await self.db.commit()
        await self.db.refresh(snapshot)
        return snapshot