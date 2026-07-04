"""纸面交易 Repository。

本文件封装纸面交易账户、配置、运行记录、持仓、订单、成交和权益快照的数据访问。
纸面交易只做虚拟模拟，不连接券商、不真实下单；Repository 只负责读写数据库，
不判断策略信号、不计算成交、不更新资金曲线。
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper_trading_account import PaperTradingAccount
from app.models.paper_trading_equity_snapshot import PaperTradingEquitySnapshot
from app.models.paper_trading_order import PaperTradingOrder
from app.models.paper_trading_position import PaperTradingPosition
from app.models.paper_trading_trade import PaperTradingTrade
from app.models.paper_trading_account_config import PaperTradingAccountConfig
from app.models.paper_trading_run import PaperTradingRun
from app.models.paper_trading_account_symbol import PaperTradingAccountSymbol
from app.models.watchlist_item import WatchlistItem
from app.schemas.paper_trading import (
    PaperTradingAccountCreate,
    PaperTradingAccountStatus,
    PaperTradingAccountUpdate,
    PaperTradingListQuery,
    PaperTradingOrderCreate,
    PaperTradingOrderStatus,
    PaperTradingAccountConfigCreate,
    PaperTradingAccountConfigUpdate,
    PaperTradingRunCreate,
    PaperTradingRunStatus,
    PaperTradingRunUpdate,
)


class AsyncPaperTradingRepository:
    """异步纸面交易数据访问对象。

    账户及子资源查询需要通过 user_id 或账户 join 做隔离，避免用户访问其他人的模拟盘数据。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_account(
        self,
        *,
        user_id: int,
        payload: PaperTradingAccountCreate,
        universe_items: list[WatchlistItem],
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
        await self.db.flush()
        self.db.add_all(
            [
                PaperTradingAccountSymbol(
                    account_id=account.id,
                    symbol=item.symbol.strip().upper(),
                    market=item.market.strip().upper(),
                    name=item.name,
                    source_watchlist_item_id=item.id,
                )
                for item in universe_items
            ]
        )
        await self.db.commit()
        await self.db.refresh(account)
        return account

    async def get_account(
        self,
        *,
        account_id: int,
        user_id: int,
    ) -> PaperTradingAccount | None:
        """查询当前用户的纸面交易账户。

        account_id 不是权限凭证，必须同时匹配 user_id。
        """

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
        """查询所有活跃纸面交易账户。

        该方法供定时任务批量推进 tick 使用，因此不按单个用户过滤。
        """

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
        previous_status = account.status

        for field, value in update_data.items():
            setattr(account, field, value)

        if payload.status == PaperTradingAccountStatus.CLOSED and previous_status != PaperTradingAccountStatus.CLOSED:
            account.closed_at = datetime.now(UTC)

        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return account

    async def delete_account_tree(
        self,
        account: PaperTradingAccount,
    ) -> None:
        """删除一个纸面交易账户及其全部虚拟子数据。

        纸面交易是模拟数据，用户可能创建大量测试账户；这里提供显式清理能力。
        按子表到父表顺序删除，避免不同数据库对级联约束支持差异导致测试和生产行为不一致。
        """

        account_id = account.id
        for model in (
            PaperTradingRun,
            PaperTradingTrade,
            PaperTradingOrder,
            PaperTradingPosition,
            PaperTradingEquitySnapshot,
            PaperTradingAccountConfig,
            PaperTradingAccountSymbol,
        ):
            await self.db.execute(
                delete(model).where(model.account_id == account_id)
            )

        await self.db.delete(account)
        await self.db.commit()

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

    async def list_account_symbols(
        self,
        *,
        account_id: int,
        limit: int = 500,
    ) -> list[PaperTradingAccountSymbol]:
        """按稳定创建顺序读取账户固定组合，不再查询实时自选股。"""

        stmt = (
            select(PaperTradingAccountSymbol)
            .where(PaperTradingAccountSymbol.account_id == account_id)
            .order_by(PaperTradingAccountSymbol.id.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_account_symbols(self, *, account_id: int) -> int:
        stmt = select(func.count(PaperTradingAccountSymbol.id)).where(
            PaperTradingAccountSymbol.account_id == account_id
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def count_open_positions(self, *, account_id: int) -> int:
        stmt = select(func.count(PaperTradingPosition.id)).where(
            PaperTradingPosition.account_id == account_id,
            PaperTradingPosition.quantity > 0,
        )
        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def create_account_config(
        self,
        *,
        account_id: int,
        payload: PaperTradingAccountConfigCreate,
    ) -> PaperTradingAccountConfig:
        config = PaperTradingAccountConfig(
            account_id=account_id,
            is_enabled=payload.is_enabled,
            max_symbols_per_tick=payload.max_symbols_per_tick,
            allow_buy=payload.allow_buy,
            allow_sell=payload.allow_sell,
            max_single_order_cash_ratio=payload.max_single_order_cash_ratio,
            max_total_position_ratio=payload.max_total_position_ratio,
            max_position_count=payload.max_position_count,
            min_order_cash_amount=payload.min_order_cash_amount,
            fee_rate=payload.fee_rate,
            enforce_data_quality=payload.enforce_data_quality,
            data_quality_stale_after_days=payload.data_quality_stale_after_days,
            notes=payload.notes,
        )

        self.db.add(config)
        await self.db.commit()
        await self.db.refresh(config)
        return config

    async def get_account_config(
        self,
        *,
        account_id: int,
        user_id: int,
    ) -> PaperTradingAccountConfig | None:
        """查询当前用户某个账户的配置。

        配置表本身没有 user_id，因此通过账户表 join 做归属校验。
        """

        stmt = (
            select(PaperTradingAccountConfig)
            .join(
                PaperTradingAccount,
                PaperTradingAccountConfig.account_id == PaperTradingAccount.id,
            )
            .where(
                PaperTradingAccountConfig.account_id == account_id,
                PaperTradingAccount.user_id == user_id,
            )
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_account_config_by_account_id(
        self,
        *,
        account_id: int,
    ) -> PaperTradingAccountConfig | None:
        stmt = select(PaperTradingAccountConfig).where(
            PaperTradingAccountConfig.account_id == account_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_account_config(
        self,
        *,
        config: PaperTradingAccountConfig,
        payload: PaperTradingAccountConfigUpdate,
    ) -> PaperTradingAccountConfig:
        update_data = payload.model_dump(
            mode="json",
            exclude_unset=True,
        )

        for field, value in update_data.items():
            setattr(config, field, value)

        self.db.add(config)
        await self.db.commit()
        await self.db.refresh(config)
        return config

    async def get_or_create_account_config(
        self,
        *,
        account_id: int,
    ) -> PaperTradingAccountConfig:
        """获取或创建账户默认配置。

        默认配置保证新账户即使没有手动配置，也能进入受控 tick 流程。
        """

        config = await self.get_account_config_by_account_id(
            account_id=account_id,
        )

        if config is not None:
            return config

        return await self.create_account_config(
            account_id=account_id,
            payload=PaperTradingAccountConfigCreate(),
        )

    async def create_run(
        self,
        *,
        payload: PaperTradingRunCreate,
    ) -> PaperTradingRun:
        """创建一次纸面交易 tick 的运行记录。"""

        run = PaperTradingRun(
            account_id=payload.account_id,
            source=payload.source,
            status=PaperTradingRunStatus.RUNNING,
            request_snapshot=payload.request_snapshot,
            account_config_snapshot=payload.account_config_snapshot,
        )

        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def get_run(
        self,
        *,
        run_id: int,
        account_id: int,
        user_id: int,
    ) -> PaperTradingRun | None:
        """查询当前用户某个账户下的运行记录。

        run 属于账户子资源，需要 join 账户表确认 user_id。
        """

        stmt = (
            select(PaperTradingRun)
            .join(
                PaperTradingAccount,
                PaperTradingRun.account_id == PaperTradingAccount.id,
            )
            .where(
                PaperTradingRun.id == run_id,
                PaperTradingRun.account_id == account_id,
                PaperTradingAccount.user_id == user_id,
            )
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_run_by_id(
        self,
        *,
        run_id: int,
    ) -> PaperTradingRun | None:
        stmt = select(PaperTradingRun).where(
            PaperTradingRun.id == run_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_run(
        self,
        *,
        account_id: int,
        user_id: int,
    ) -> PaperTradingRun | None:
        stmt = (
            select(PaperTradingRun)
            .join(
                PaperTradingAccount,
                PaperTradingRun.account_id == PaperTradingAccount.id,
            )
            .where(
                PaperTradingRun.account_id == account_id,
                PaperTradingAccount.user_id == user_id,
            )
            .order_by(PaperTradingRun.started_at.desc())
            .limit(1)
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_runs(
        self,
        *,
        account_id: int,
        user_id: int,
        query: PaperTradingListQuery,
    ) -> list[PaperTradingRun]:
        """分页查询当前用户某个账户的 tick 运行记录。"""

        stmt = (
            select(PaperTradingRun)
            .join(
                PaperTradingAccount,
                PaperTradingRun.account_id == PaperTradingAccount.id,
            )
            .where(
                PaperTradingRun.account_id == account_id,
                PaperTradingAccount.user_id == user_id,
            )
            .order_by(PaperTradingRun.started_at.desc())
            .offset(query.offset)
            .limit(query.limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_runs(
        self,
        *,
        account_id: int,
        user_id: int,
    ) -> int:
        stmt = (
            select(func.count(PaperTradingRun.id))
            .join(
                PaperTradingAccount,
                PaperTradingRun.account_id == PaperTradingAccount.id,
            )
            .where(
                PaperTradingRun.account_id == account_id,
                PaperTradingAccount.user_id == user_id,
            )
        )

        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def update_run(
        self,
        *,
        run: PaperTradingRun,
        payload: PaperTradingRunUpdate,
        finished_at: datetime | None = None,
    ) -> PaperTradingRun:
        update_data = payload.model_dump(
            mode="json",
            exclude_unset=True,
        )

        for field, value in update_data.items():
            setattr(run, field, value)

        if finished_at is not None:
            run.finished_at = finished_at

        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run

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
        """分页查询当前用户某个账户的模拟持仓。"""

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

    async def list_open_positions_for_account(
        self,
        *,
        account_id: int,
        limit: int = 500,
    ) -> list[PaperTradingPosition]:
        """读取仍有数量的持仓，供移出自选股后的退出监控使用。"""

        stmt = (
            select(PaperTradingPosition)
            .where(
                PaperTradingPosition.account_id == account_id,
                PaperTradingPosition.quantity > 0,
            )
            .order_by(PaperTradingPosition.updated_at.desc())
            .limit(limit)
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
        """创建模拟订单。

        订单只是纸面交易内部记录，不会发送到真实券商。
        """

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
        """分页查询当前用户某个账户的模拟订单。"""

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
        """创建模拟成交记录。

        成交价格和数量由 Service 层计算，Repository 只负责落库。
        """

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
        """分页查询当前用户某个账户的模拟成交。"""

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
        """创建权益快照。

        快照保存某一日现金、持仓市值、总权益、收益率和回撤，用于绘制模拟盘权益曲线。
        """

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
        """分页查询当前用户某个账户的权益快照。"""

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
