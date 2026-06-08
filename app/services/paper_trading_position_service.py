from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper_trading_account import PaperTradingAccount
from app.models.paper_trading_position import PaperTradingPosition
from app.models.paper_trading_trade import PaperTradingTrade
from app.repositories.paper_trading_repo import AsyncPaperTradingRepository
from app.schemas.paper_trading import PaperTradingOrderSide
from app.services.paper_trading_order_service import (
    PaperTradingOrderExecutionItem,
    PaperTradingOrderExecutionResult,
)


@dataclass(slots=True)
class PaperTradingPositionUpdateItem:
    symbol: str
    market: str
    side: str
    trade_id: int | None = None
    position: PaperTradingPosition | None = None
    cash_before: Decimal = Decimal("0")
    cash_after: Decimal = Decimal("0")
    message: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PaperTradingPositionUpdateResult:
    account_id: int
    cash_before: Decimal
    cash_after: Decimal
    updated_position_count: int
    items: list[PaperTradingPositionUpdateItem]
    warnings: list[str] = field(default_factory=list)


class PaperTradingPositionService:
    """Update paper trading account cash and positions from simulated trades.

    This service consumes trades created by PaperTradingOrderService.
    It does not create orders, trades, or equity snapshots.
    """

    QUANTITY_PRECISION = Decimal("0.000001")
    MONEY_PRECISION = Decimal("0.0001")
    RETURN_PRECISION = Decimal("0.00000001")

    def __init__(
        self,
        db: AsyncSession,
        *,
        repository: AsyncPaperTradingRepository | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or AsyncPaperTradingRepository(db)

    async def apply_execution_result(
        self,
        *,
        account: PaperTradingAccount,
        execution_result: PaperTradingOrderExecutionResult,
    ) -> PaperTradingPositionUpdateResult:
        cash_before = self._to_decimal(account.cash_balance)
        current_cash = cash_before

        items: list[PaperTradingPositionUpdateItem] = []
        warnings: list[str] = []

        for execution_item in execution_result.items:
            if execution_item.trade is None:
                continue

            update_item, current_cash = await self._apply_execution_item(
                account=account,
                execution_item=execution_item,
                current_cash=current_cash,
            )
            items.append(update_item)
            warnings.extend(update_item.warnings)

        updated_account = await self.repository.update_account_cash(
            account=account,
            cash_balance=self._quantize_money(current_cash),
        )

        return PaperTradingPositionUpdateResult(
            account_id=account.id,
            cash_before=cash_before,
            cash_after=self._to_decimal(updated_account.cash_balance),
            updated_position_count=sum(1 for item in items if item.position is not None),
            items=items,
            warnings=self._deduplicate_messages(warnings),
        )

    async def _apply_execution_item(
        self,
        *,
        account: PaperTradingAccount,
        execution_item: PaperTradingOrderExecutionItem,
        current_cash: Decimal,
    ) -> tuple[PaperTradingPositionUpdateItem, Decimal]:
        trade = execution_item.trade
        if trade is None:
            return (
                PaperTradingPositionUpdateItem(
                    symbol=execution_item.symbol,
                    market=execution_item.market,
                    side=execution_item.action,
                    cash_before=current_cash,
                    cash_after=current_cash,
                    message="没有成交记录，跳过持仓和资金更新。",
                ),
                current_cash,
            )

        if trade.side == PaperTradingOrderSide.BUY:
            return await self._apply_buy_trade(
                account=account,
                trade=trade,
                current_cash=current_cash,
            )

        if trade.side == PaperTradingOrderSide.SELL:
            return await self._apply_sell_trade(
                account=account,
                trade=trade,
                current_cash=current_cash,
            )

        return (
            PaperTradingPositionUpdateItem(
                symbol=trade.symbol,
                market=trade.market,
                side=trade.side,
                trade_id=trade.id,
                cash_before=current_cash,
                cash_after=current_cash,
                message="未知成交方向，跳过持仓和资金更新。",
                warnings=[f"未知成交方向：{trade.side}"],
            ),
            current_cash,
        )

    async def _apply_buy_trade(
        self,
        *,
        account: PaperTradingAccount,
        trade: PaperTradingTrade,
        current_cash: Decimal,
    ) -> tuple[PaperTradingPositionUpdateItem, Decimal]:
        trade_value = self._to_decimal(trade.trade_value)
        fee_amount = self._to_decimal(trade.fee_amount)
        total_cost = self._quantize_money(trade_value + fee_amount)

        cash_after = self._quantize_money(current_cash - total_cost)
        warnings: list[str] = []

        if cash_after < 0:
            warnings.append("买入成交后现金小于 0，已将现金修正为 0。")
            cash_after = Decimal("0")

        position = await self.repository.get_position(
            account_id=account.id,
            symbol=trade.symbol,
            market=trade.market,
        )

        if position is None:
            updated_position = await self._create_buy_position(
                account=account,
                trade=trade,
                total_cost=total_cost,
            )
        else:
            updated_position = await self._increase_position(
                position=position,
                trade=trade,
                total_cost=total_cost,
            )

        return (
            PaperTradingPositionUpdateItem(
                symbol=trade.symbol,
                market=trade.market,
                side=trade.side,
                trade_id=trade.id,
                position=updated_position,
                cash_before=current_cash,
                cash_after=cash_after,
                message="买入成交已更新现金和持仓。",
                warnings=warnings,
            ),
            cash_after,
        )

    async def _apply_sell_trade(
        self,
        *,
        account: PaperTradingAccount,
        trade: PaperTradingTrade,
        current_cash: Decimal,
    ) -> tuple[PaperTradingPositionUpdateItem, Decimal]:
        trade_value = self._to_decimal(trade.trade_value)
        fee_amount = self._to_decimal(trade.fee_amount)
        cash_inflow = self._quantize_money(trade_value - fee_amount)
        cash_after = self._quantize_money(current_cash + cash_inflow)

        position = await self.repository.get_position(
            account_id=account.id,
            symbol=trade.symbol,
            market=trade.market,
        )

        if position is None:
            return (
                PaperTradingPositionUpdateItem(
                    symbol=trade.symbol,
                    market=trade.market,
                    side=trade.side,
                    trade_id=trade.id,
                    cash_before=current_cash,
                    cash_after=cash_after,
                    message="卖出成交没有找到原持仓，仅更新现金。",
                    warnings=["卖出成交没有找到原持仓。"],
                ),
                cash_after,
            )

        updated_position = await self._decrease_position(
            position=position,
            trade=trade,
        )

        return (
            PaperTradingPositionUpdateItem(
                symbol=trade.symbol,
                market=trade.market,
                side=trade.side,
                trade_id=trade.id,
                position=updated_position,
                cash_before=current_cash,
                cash_after=cash_after,
                message="卖出成交已更新现金和持仓。",
            ),
            cash_after,
        )

    async def _create_buy_position(
        self,
        *,
        account: PaperTradingAccount,
        trade: PaperTradingTrade,
        total_cost: Decimal,
    ) -> PaperTradingPosition:
        quantity = self._quantize_quantity(self._to_decimal(trade.filled_quantity))
        avg_cost = self._calculate_avg_cost(
            total_cost=total_cost,
            quantity=quantity,
        )
        last_price = self._to_decimal(trade.filled_price)
        market_value = self._calculate_market_value(
            quantity=quantity,
            last_price=last_price,
        )
        unrealized_pnl = self._calculate_unrealized_pnl(
            quantity=quantity,
            avg_cost=avg_cost,
            market_value=market_value,
        )
        unrealized_return = self._calculate_unrealized_return(
            quantity=quantity,
            avg_cost=avg_cost,
            unrealized_pnl=unrealized_pnl,
        )

        return await self.repository.create_position(
            account_id=account.id,
            symbol=trade.symbol,
            market=trade.market,
            quantity=quantity,
            avg_cost=avg_cost,
            last_price=last_price,
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
            unrealized_return=unrealized_return,
        )

    async def _increase_position(
        self,
        *,
        position: PaperTradingPosition,
        trade: PaperTradingTrade,
        total_cost: Decimal,
    ) -> PaperTradingPosition:
        old_quantity = self._to_decimal(position.quantity)
        buy_quantity = self._to_decimal(trade.filled_quantity)
        new_quantity = self._quantize_quantity(old_quantity + buy_quantity)

        old_cost = old_quantity * self._to_decimal(position.avg_cost)
        new_total_cost = old_cost + total_cost
        avg_cost = self._calculate_avg_cost(
            total_cost=new_total_cost,
            quantity=new_quantity,
        )

        last_price = self._to_decimal(trade.filled_price)
        market_value = self._calculate_market_value(
            quantity=new_quantity,
            last_price=last_price,
        )
        unrealized_pnl = self._calculate_unrealized_pnl(
            quantity=new_quantity,
            avg_cost=avg_cost,
            market_value=market_value,
        )
        unrealized_return = self._calculate_unrealized_return(
            quantity=new_quantity,
            avg_cost=avg_cost,
            unrealized_pnl=unrealized_pnl,
        )

        return await self.repository.update_position(
            position=position,
            quantity=new_quantity,
            avg_cost=avg_cost,
            last_price=last_price,
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
            unrealized_return=unrealized_return,
        )

    async def _decrease_position(
        self,
        *,
        position: PaperTradingPosition,
        trade: PaperTradingTrade,
    ) -> PaperTradingPosition:
        old_quantity = self._to_decimal(position.quantity)
        sell_quantity = self._to_decimal(trade.filled_quantity)
        remaining_quantity = self._quantize_quantity(old_quantity - sell_quantity)

        if remaining_quantity < 0:
            remaining_quantity = Decimal("0")

        last_price = self._to_decimal(trade.filled_price)

        if remaining_quantity == 0:
            avg_cost = Decimal("0")
            market_value = Decimal("0")
            unrealized_pnl = Decimal("0")
            unrealized_return = None
        else:
            avg_cost = self._to_decimal(position.avg_cost)
            market_value = self._calculate_market_value(
                quantity=remaining_quantity,
                last_price=last_price,
            )
            unrealized_pnl = self._calculate_unrealized_pnl(
                quantity=remaining_quantity,
                avg_cost=avg_cost,
                market_value=market_value,
            )
            unrealized_return = self._calculate_unrealized_return(
                quantity=remaining_quantity,
                avg_cost=avg_cost,
                unrealized_pnl=unrealized_pnl,
            )

        return await self.repository.update_position(
            position=position,
            quantity=remaining_quantity,
            avg_cost=avg_cost,
            last_price=last_price,
            market_value=market_value,
            unrealized_pnl=unrealized_pnl,
            unrealized_return=unrealized_return,
        )

    def _calculate_avg_cost(
        self,
        *,
        total_cost: Decimal,
        quantity: Decimal,
    ) -> Decimal:
        if quantity <= 0:
            return Decimal("0")

        return self._quantize_money(total_cost / quantity)

    def _calculate_market_value(
        self,
        *,
        quantity: Decimal,
        last_price: Decimal,
    ) -> Decimal:
        return self._quantize_money(quantity * last_price)

    def _calculate_unrealized_pnl(
        self,
        *,
        quantity: Decimal,
        avg_cost: Decimal,
        market_value: Decimal,
    ) -> Decimal:
        cost_basis = self._quantize_money(quantity * avg_cost)
        return self._quantize_money(market_value - cost_basis)

    def _calculate_unrealized_return(
        self,
        *,
        quantity: Decimal,
        avg_cost: Decimal,
        unrealized_pnl: Decimal,
    ) -> Decimal | None:
        cost_basis = self._quantize_money(quantity * avg_cost)
        if cost_basis <= 0:
            return None

        return self._quantize_return(unrealized_pnl / cost_basis)

    def _to_decimal(
        self,
        value,
    ) -> Decimal:
        return Decimal(str(value))

    def _quantize_quantity(
        self,
        value: Decimal,
    ) -> Decimal:
        return value.quantize(
            self.QUANTITY_PRECISION,
            rounding=ROUND_DOWN,
        )

    def _quantize_money(
        self,
        value: Decimal,
    ) -> Decimal:
        return value.quantize(
            self.MONEY_PRECISION,
            rounding=ROUND_DOWN,
        )

    def _quantize_return(
        self,
        value: Decimal,
    ) -> Decimal:
        return value.quantize(
            self.RETURN_PRECISION,
            rounding=ROUND_DOWN,
        )

    def _deduplicate_messages(
        self,
        messages: list[str],
    ) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []

        for message in messages:
            normalized = message.strip()
            if not normalized or normalized in seen:
                continue

            seen.add(normalized)
            result.append(normalized)

        return result