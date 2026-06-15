"""纸面交易订单与成交专项测试。

验证 buy / sell 信号如何生成虚拟订单和虚拟成交。
本文件不测试真实资金、不连接券商，也不真实下单。
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select

from app.models.paper_trading_order import PaperTradingOrder
from app.models.paper_trading_trade import PaperTradingTrade
from app.repositories.paper_trading_repo import AsyncPaperTradingRepository
from app.schemas.market import (
    MarketIndicatorResponse,
    MarketOverviewResponse,
    MarketQuoteResponse,
)
from app.schemas.market_data_sync import MarketDataQualityReport
from app.schemas.paper_trading import (
    PaperTradingAccountCreate,
    PaperTradingOrderSide,
    PaperTradingOrderStatus,
    PaperTradingTickRequest,
)
from app.schemas.strategy_signal import StrategySignalResponse
from app.services.paper_trading_account_service import PaperTradingAccountService
from app.services.paper_trading_order_service import PaperTradingOrderService
from app.services.paper_trading_signal_service import (
    PaperTradingSignalContext,
    PaperTradingSignalItem,
)


async def _create_account(db_session, user_id: int, initial_cash: Decimal = Decimal("100000")):
    account_service = PaperTradingAccountService(db_session)

    response = await account_service.create_account(
        user_id=user_id,
        request=PaperTradingAccountCreate(
            name="量化专项纸面交易账户",
            initial_cash=initial_cash,
            currency="CNY",
        ),
    )

    return await account_service.get_account_model(
        user_id=user_id,
        account_id=response.id,
    )


def _overview(
    *,
    symbol: str,
    signal: str,
    latest_price: float,
) -> MarketOverviewResponse:
    return MarketOverviewResponse(
        quote=MarketQuoteResponse(
            symbol=symbol,
            market="US",
            name=f"{symbol} Test",
            currency="USD",
            latest_price=latest_price,
            previous_close=latest_price - 1,
            open_price=latest_price - 0.5,
            high_price=latest_price + 1,
            low_price=latest_price - 1,
            volume=1000000,
            price_change=1,
            price_change_percent=1,
            as_of=datetime.now(UTC),
            source="mock",
        ),
        indicators=MarketIndicatorResponse(
            symbol=symbol,
            market="US",
            price_change=1,
            price_change_percent=1,
            moving_average_5=latest_price,
            moving_average_20=latest_price - 1,
            volatility_level="medium",
            trend="bullish" if signal == "buy" else "bearish",
            source="mock",
        ),
        data_quality=MarketDataQualityReport(
            symbol=symbol,
            market="US",
            timeframe="1d",
            source="mock",
            adjust_type="none",
            candle_count=40,
            is_empty=False,
            is_enough=True,
            is_stale=False,
            errors=[],
            warnings=[],
        ),
        strategy_signal=StrategySignalResponse(
            symbol=symbol,
            market="US",
            timeframe="1d",
            adjust_type="none",
            source="mock",
            status="available",
            signal=signal,
            strength="strong",
            score=95 if signal == "buy" else 5,
            summary=f"{signal} signal for paper trading test",
            reasons=[f"{signal} reason"],
            risks=[],
        ),
    )


def _signal_item(
    *,
    symbol: str,
    action: str,
    latest_price: float,
) -> PaperTradingSignalItem:
    return PaperTradingSignalItem(
        symbol=symbol,
        market="US",
        name=f"{symbol} Test",
        overview=_overview(
            symbol=symbol,
            signal=action,
            latest_price=latest_price,
        ),
        can_generate_order=True,
        action=action,
        reason=f"{action} signal reason",
    )


def _signal_context(
    *,
    user_id: int,
    items: list[PaperTradingSignalItem],
) -> PaperTradingSignalContext:
    return PaperTradingSignalContext(
        user_id=user_id,
        request=PaperTradingTickRequest(
            force=True,
            max_symbols=len(items) or 1,
            notify=False,
        ),
        universe_items=[],
        items=items,
        actionable_items=items,
    )


async def _count_rows(db_session, model) -> int:
    result = await db_session.execute(select(func.count(model.id)))
    return int(result.scalar_one())


async def test_buy_signal_creates_filled_order_and_trade(db_session, test_user) -> None:
    account = await _create_account(db_session, user_id=test_user.id)
    service = PaperTradingOrderService(db_session)

    signal_item = _signal_item(
        symbol="PBUY",
        action="buy",
        latest_price=100,
    )

    result = await service.execute_signal_orders(
        account=account,
        signal_context=_signal_context(
            user_id=test_user.id,
            items=[signal_item],
        ),
    )

    assert result.account_id == account.id
    assert result.signal_count == 1
    assert result.order_count == 1
    assert result.trade_count == 1
    assert result.warnings == []

    item = result.items[0]
    assert item.status == "filled"
    assert item.order is not None
    assert item.trade is not None

    order = item.order
    trade = item.trade

    assert order.side == PaperTradingOrderSide.BUY
    assert order.status == PaperTradingOrderStatus.FILLED
    assert order.symbol == "PBUY"
    assert order.market == "US"
    assert order.planned_quantity == Decimal("100.000000")
    assert order.planned_price == Decimal("100.0000")
    assert order.filled_quantity == Decimal("100.000000")
    assert order.filled_price == Decimal("100.0000")
    assert order.signal_source == "strategy_signal"
    assert order.signal_snapshot["strategy_signal"]["signal"] == "buy"
    assert order.reason == "buy signal reason"

    assert trade.order_id == order.id
    assert trade.side == PaperTradingOrderSide.BUY
    assert trade.filled_quantity == Decimal("100.000000")
    assert trade.filled_price == Decimal("100.0000")
    assert trade.trade_value == Decimal("10000.0000")
    assert trade.fee_amount == Decimal("3.0000")

    assert await _count_rows(db_session, PaperTradingOrder) == 1
    assert await _count_rows(db_session, PaperTradingTrade) == 1

    refreshed_account = await PaperTradingAccountService(db_session).get_account_model(
        user_id=test_user.id,
        account_id=account.id,
    )
    assert refreshed_account.cash_balance == Decimal("100000.0000")


async def test_multiple_buy_signals_use_remaining_virtual_cash_inside_execution(db_session, test_user) -> None:
    account = await _create_account(db_session, user_id=test_user.id)
    service = PaperTradingOrderService(db_session)

    result = await service.execute_signal_orders(
        account=account,
        signal_context=_signal_context(
            user_id=test_user.id,
            items=[
                _signal_item(symbol="PB1", action="buy", latest_price=100),
                _signal_item(symbol="PB2", action="buy", latest_price=100),
            ],
        ),
    )

    assert result.signal_count == 2
    assert result.order_count == 2
    assert result.trade_count == 2

    first_trade = result.items[0].trade
    second_trade = result.items[1].trade

    assert first_trade is not None
    assert second_trade is not None
    assert first_trade.trade_value == Decimal("10000.0000")
    assert second_trade.trade_value < first_trade.trade_value
    assert second_trade.fee_amount > Decimal("0")


async def test_sell_signal_creates_filled_order_and_trade_when_position_exists(db_session, test_user) -> None:
    account = await _create_account(db_session, user_id=test_user.id)
    repository = AsyncPaperTradingRepository(db_session)

    await repository.create_position(
        account_id=account.id,
        symbol="PSELL",
        market="US",
        quantity=Decimal("12.5"),
        avg_cost=Decimal("90"),
        last_price=Decimal("100"),
        market_value=Decimal("1250"),
        unrealized_pnl=Decimal("125"),
        unrealized_return=Decimal("0.10"),
    )

    service = PaperTradingOrderService(db_session)

    result = await service.execute_signal_orders(
        account=account,
        signal_context=_signal_context(
            user_id=test_user.id,
            items=[
                _signal_item(
                    symbol="PSELL",
                    action="sell",
                    latest_price=110,
                )
            ],
        ),
    )

    assert result.signal_count == 1
    assert result.order_count == 1
    assert result.trade_count == 1

    item = result.items[0]
    assert item.status == "filled"
    assert item.order is not None
    assert item.trade is not None

    order = item.order
    trade = item.trade

    assert order.side == PaperTradingOrderSide.SELL
    assert order.status == PaperTradingOrderStatus.FILLED
    assert order.planned_quantity == Decimal("12.500000")
    assert order.planned_price == Decimal("110.0000")
    assert order.filled_quantity == Decimal("12.500000")
    assert order.filled_price == Decimal("110.0000")
    assert order.signal_snapshot["strategy_signal"]["signal"] == "sell"

    assert trade.side == PaperTradingOrderSide.SELL
    assert trade.filled_quantity == Decimal("12.500000")
    assert trade.filled_price == Decimal("110.0000")
    assert trade.trade_value == Decimal("1375.0000")
    assert trade.fee_amount == Decimal("0.4125")


async def test_sell_signal_without_position_is_skipped(db_session, test_user) -> None:
    account = await _create_account(db_session, user_id=test_user.id)
    service = PaperTradingOrderService(db_session)

    result = await service.execute_signal_orders(
        account=account,
        signal_context=_signal_context(
            user_id=test_user.id,
            items=[
                _signal_item(
                    symbol="PNONE",
                    action="sell",
                    latest_price=50,
                )
            ],
        ),
    )

    assert result.signal_count == 1
    assert result.order_count == 0
    assert result.trade_count == 0

    item = result.items[0]
    assert item.status == "skipped"
    assert item.order is None
    assert item.trade is None
    assert item.message == "当前没有可卖出的模拟持仓，跳过卖出模拟订单。"

    assert await _count_rows(db_session, PaperTradingOrder) == 0
    assert await _count_rows(db_session, PaperTradingTrade) == 0


async def test_buy_signal_without_valid_price_is_skipped(db_session, test_user) -> None:
    account = await _create_account(db_session, user_id=test_user.id)
    service = PaperTradingOrderService(db_session)

    result = await service.execute_signal_orders(
        account=account,
        signal_context=_signal_context(
            user_id=test_user.id,
            items=[
                _signal_item(
                    symbol="PZERO",
                    action="buy",
                    latest_price=0,
                )
            ],
        ),
    )

    assert result.signal_count == 1
    assert result.order_count == 0
    assert result.trade_count == 0

    item = result.items[0]
    assert item.status == "skipped"
    assert item.order is None
    assert item.trade is None
    assert item.message == "缺少有效最新价格，跳过买入模拟订单。"

    assert await _count_rows(db_session, PaperTradingOrder) == 0
    assert await _count_rows(db_session, PaperTradingTrade) == 0


async def test_non_buy_sell_action_is_skipped_even_if_passed_to_order_service(db_session, test_user) -> None:
    account = await _create_account(db_session, user_id=test_user.id)
    service = PaperTradingOrderService(db_session)

    hold_item = _signal_item(
        symbol="PHOLD",
        action="hold",
        latest_price=100,
    )

    result = await service.execute_signal_orders(
        account=account,
        signal_context=_signal_context(
            user_id=test_user.id,
            items=[hold_item],
        ),
    )

    assert result.signal_count == 1
    assert result.order_count == 0
    assert result.trade_count == 0

    item = result.items[0]
    assert item.status == "skipped"
    assert item.action == "hold"
    assert item.order is None
    assert item.trade is None
    assert item.message == "当前信号不是 buy / sell，跳过模拟订单生成。"
