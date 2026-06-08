from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, ROUND_DOWN
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper_trading_account import PaperTradingAccount
from app.models.paper_trading_order import PaperTradingOrder
from app.models.paper_trading_trade import PaperTradingTrade
from app.repositories.paper_trading_repo import AsyncPaperTradingRepository
from app.schemas.paper_trading import (
    PaperTradingOrderCreate,
    PaperTradingOrderSide,
    PaperTradingOrderStatus,
    PaperTradingSignalSource,
)
from app.services.paper_trading_signal_service import (
    PaperTradingSignalContext,
    PaperTradingSignalItem,
)


@dataclass(slots=True)
class PaperTradingOrderExecutionItem:
    symbol: str
    market: str
    action: str
    order: PaperTradingOrder | None = None
    trade: PaperTradingTrade | None = None
    status: str = "skipped"
    message: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PaperTradingOrderExecutionResult:
    account_id: int
    signal_count: int
    order_count: int
    trade_count: int
    items: list[PaperTradingOrderExecutionItem]
    warnings: list[str] = field(default_factory=list)


class PaperTradingOrderService:
    """Create simulated paper trading orders and trades.

    This service creates order and trade rows only.
    It does not update account cash, positions, or equity snapshots.
    """

    BUY_CASH_RATIO = Decimal("0.10")
    MAX_BUY_CASH_RATIO = Decimal("0.30")
    FEE_RATE = Decimal("0.0003")
    QUANTITY_PRECISION = Decimal("0.000001")
    MONEY_PRECISION = Decimal("0.0001")

    def __init__(
        self,
        db: AsyncSession,
        *,
        repository: AsyncPaperTradingRepository | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or AsyncPaperTradingRepository(db)

    async def execute_signal_orders(
        self,
        *,
        account: PaperTradingAccount,
        signal_context: PaperTradingSignalContext,
    ) -> PaperTradingOrderExecutionResult:
        warnings: list[str] = []
        items: list[PaperTradingOrderExecutionItem] = []

        available_cash = Decimal(account.cash_balance)

        for signal_item in signal_context.actionable_items:
            execution_item, available_cash = await self._execute_one_signal(
                account=account,
                signal_item=signal_item,
                available_cash=available_cash,
            )
            items.append(execution_item)
            warnings.extend(execution_item.warnings)

        order_count = sum(1 for item in items if item.order is not None)
        trade_count = sum(1 for item in items if item.trade is not None)

        return PaperTradingOrderExecutionResult(
            account_id=account.id,
            signal_count=len(signal_context.actionable_items),
            order_count=order_count,
            trade_count=trade_count,
            items=items,
            warnings=self._deduplicate_messages(warnings),
        )

    async def _execute_one_signal(
        self,
        *,
        account: PaperTradingAccount,
        signal_item: PaperTradingSignalItem,
        available_cash: Decimal,
    ) -> tuple[PaperTradingOrderExecutionItem, Decimal]:
        if signal_item.action == PaperTradingOrderSide.BUY:
            return await self._execute_buy_signal(
                account=account,
                signal_item=signal_item,
                available_cash=available_cash,
            )

        if signal_item.action == PaperTradingOrderSide.SELL:
            return await self._execute_sell_signal(
                account=account,
                signal_item=signal_item,
                available_cash=available_cash,
            )

        return (
            PaperTradingOrderExecutionItem(
                symbol=signal_item.symbol,
                market=signal_item.market,
                action=signal_item.action or "unknown",
                status=PaperTradingOrderStatus.SKIPPED,
                message="当前信号不是 buy / sell，跳过模拟订单生成。",
            ),
            available_cash,
        )

    async def _execute_buy_signal(
        self,
        *,
        account: PaperTradingAccount,
        signal_item: PaperTradingSignalItem,
        available_cash: Decimal,
    ) -> tuple[PaperTradingOrderExecutionItem, Decimal]:
        latest_price = self._get_latest_price(signal_item)
        if latest_price is None or latest_price <= 0:
            return (
                PaperTradingOrderExecutionItem(
                    symbol=signal_item.symbol,
                    market=signal_item.market,
                    action=PaperTradingOrderSide.BUY,
                    status=PaperTradingOrderStatus.SKIPPED,
                    message="缺少有效最新价格，跳过买入模拟订单。",
                ),
                available_cash,
            )

        planned_cash = self._calculate_buy_cash(available_cash)
        if planned_cash <= 0:
            return (
                PaperTradingOrderExecutionItem(
                    symbol=signal_item.symbol,
                    market=signal_item.market,
                    action=PaperTradingOrderSide.BUY,
                    status=PaperTradingOrderStatus.SKIPPED,
                    message="当前可用虚拟现金不足，跳过买入模拟订单。",
                ),
                available_cash,
            )

        planned_quantity = self._quantize_quantity(planned_cash / latest_price)
        if planned_quantity <= 0:
            return (
                PaperTradingOrderExecutionItem(
                    symbol=signal_item.symbol,
                    market=signal_item.market,
                    action=PaperTradingOrderSide.BUY,
                    status=PaperTradingOrderStatus.SKIPPED,
                    message="计算出的买入数量为 0，跳过买入模拟订单。",
                ),
                available_cash,
            )

        trade_value = self._quantize_money(planned_quantity * latest_price)
        fee_amount = self._calculate_fee(trade_value)
        total_cost = trade_value + fee_amount

        if total_cost > available_cash:
            planned_quantity = self._quantize_quantity(
                available_cash / (latest_price * (Decimal("1") + self.FEE_RATE))
            )
            trade_value = self._quantize_money(planned_quantity * latest_price)
            fee_amount = self._calculate_fee(trade_value)
            total_cost = trade_value + fee_amount

        if planned_quantity <= 0 or total_cost > available_cash:
            return (
                PaperTradingOrderExecutionItem(
                    symbol=signal_item.symbol,
                    market=signal_item.market,
                    action=PaperTradingOrderSide.BUY,
                    status=PaperTradingOrderStatus.SKIPPED,
                    message="扣除模拟手续费后现金不足，跳过买入模拟订单。",
                ),
                available_cash,
            )

        order = await self._create_order(
            account=account,
            signal_item=signal_item,
            side=PaperTradingOrderSide.BUY,
            planned_quantity=planned_quantity,
            planned_price=latest_price,
        )

        trade = await self._create_trade_and_mark_filled(
            account=account,
            order=order,
            side=PaperTradingOrderSide.BUY,
            filled_quantity=planned_quantity,
            filled_price=latest_price,
            trade_value=trade_value,
            fee_amount=fee_amount,
        )

        remaining_cash = available_cash - total_cost

        return (
            PaperTradingOrderExecutionItem(
                symbol=signal_item.symbol,
                market=signal_item.market,
                action=PaperTradingOrderSide.BUY,
                order=order,
                trade=trade,
                status=PaperTradingOrderStatus.FILLED,
                message="已根据 buy 信号生成模拟买入订单并按最新价模拟成交。",
            ),
            remaining_cash,
        )

    async def _execute_sell_signal(
        self,
        *,
        account: PaperTradingAccount,
        signal_item: PaperTradingSignalItem,
        available_cash: Decimal,
    ) -> tuple[PaperTradingOrderExecutionItem, Decimal]:
        latest_price = self._get_latest_price(signal_item)
        if latest_price is None or latest_price <= 0:
            return (
                PaperTradingOrderExecutionItem(
                    symbol=signal_item.symbol,
                    market=signal_item.market,
                    action=PaperTradingOrderSide.SELL,
                    status=PaperTradingOrderStatus.SKIPPED,
                    message="缺少有效最新价格，跳过卖出模拟订单。",
                ),
                available_cash,
            )

        position = await self.repository.get_position(
            account_id=account.id,
            symbol=signal_item.symbol,
            market=signal_item.market,
        )

        if position is None or position.quantity <= 0:
            return (
                PaperTradingOrderExecutionItem(
                    symbol=signal_item.symbol,
                    market=signal_item.market,
                    action=PaperTradingOrderSide.SELL,
                    status=PaperTradingOrderStatus.SKIPPED,
                    message="当前没有可卖出的模拟持仓，跳过卖出模拟订单。",
                ),
                available_cash,
            )

        planned_quantity = self._quantize_quantity(Decimal(position.quantity))
        trade_value = self._quantize_money(planned_quantity * latest_price)
        fee_amount = self._calculate_fee(trade_value)

        order = await self._create_order(
            account=account,
            signal_item=signal_item,
            side=PaperTradingOrderSide.SELL,
            planned_quantity=planned_quantity,
            planned_price=latest_price,
        )

        trade = await self._create_trade_and_mark_filled(
            account=account,
            order=order,
            side=PaperTradingOrderSide.SELL,
            filled_quantity=planned_quantity,
            filled_price=latest_price,
            trade_value=trade_value,
            fee_amount=fee_amount,
        )

        return (
            PaperTradingOrderExecutionItem(
                symbol=signal_item.symbol,
                market=signal_item.market,
                action=PaperTradingOrderSide.SELL,
                order=order,
                trade=trade,
                status=PaperTradingOrderStatus.FILLED,
                message="已根据 sell 信号生成模拟卖出订单并按最新价模拟成交。",
            ),
            available_cash,
        )

    async def _create_order(
        self,
        *,
        account: PaperTradingAccount,
        signal_item: PaperTradingSignalItem,
        side: PaperTradingOrderSide,
        planned_quantity: Decimal,
        planned_price: Decimal,
    ) -> PaperTradingOrder:
        return await self.repository.create_order(
            PaperTradingOrderCreate(
                account_id=account.id,
                symbol=signal_item.symbol,
                market=signal_item.market,
                side=side,
                planned_quantity=planned_quantity,
                planned_price=planned_price,
                signal_source=PaperTradingSignalSource.STRATEGY_SIGNAL,
                signal_snapshot=self._build_signal_snapshot(signal_item),
                reason=self._build_order_reason(signal_item),
            )
        )

    async def _create_trade_and_mark_filled(
        self,
        *,
        account: PaperTradingAccount,
        order: PaperTradingOrder,
        side: PaperTradingOrderSide,
        filled_quantity: Decimal,
        filled_price: Decimal,
        trade_value: Decimal,
        fee_amount: Decimal,
    ) -> PaperTradingTrade:
        trade = await self.repository.create_trade(
            account_id=account.id,
            order_id=order.id,
            symbol=order.symbol,
            market=order.market,
            side=side,
            filled_quantity=filled_quantity,
            filled_price=filled_price,
            trade_value=trade_value,
            fee_amount=fee_amount,
            traded_at=datetime.now(UTC),
        )

        await self.repository.mark_order_filled(
            order=order,
            filled_quantity=filled_quantity,
            filled_price=filled_price,
        )

        return trade

    def _calculate_buy_cash(
        self,
        available_cash: Decimal,
    ) -> Decimal:
        planned_cash = available_cash * self.BUY_CASH_RATIO
        max_cash = available_cash * self.MAX_BUY_CASH_RATIO

        return self._quantize_money(min(planned_cash, max_cash))

    def _calculate_fee(
        self,
        trade_value: Decimal,
    ) -> Decimal:
        return self._quantize_money(trade_value * self.FEE_RATE)

    def _get_latest_price(
        self,
        signal_item: PaperTradingSignalItem,
    ) -> Decimal | None:
        quote = signal_item.quote
        if quote is None:
            return None

        return self._to_decimal(quote.latest_price)

    def _build_signal_snapshot(
        self,
        signal_item: PaperTradingSignalItem,
    ) -> dict[str, Any]:
        overview = signal_item.overview
        if overview is None:
            return {}

        return {
            "symbol": signal_item.symbol,
            "market": signal_item.market,
            "action": signal_item.action,
            "reason": signal_item.reason,
            "quote": (
                overview.quote.model_dump(mode="json")
                if overview.quote is not None
                else None
            ),
            "data_quality": (
                overview.data_quality.model_dump(mode="json")
                if overview.data_quality is not None
                else None
            ),
            "strategy_signal": (
                overview.strategy_signal.model_dump(mode="json")
                if overview.strategy_signal is not None
                else None
            ),
            "warnings": signal_item.warnings,
            "errors": signal_item.errors,
        }

    def _build_order_reason(
        self,
        signal_item: PaperTradingSignalItem,
    ) -> str:
        reason = signal_item.reason or "根据策略信号生成纸面交易模拟订单。"
        return reason[:500]

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