"""纸面交易资金、持仓和权益一致性测试。

验证虚拟成交如何更新模拟现金、持仓成本、市值、浮盈亏和权益快照。
纸面交易只服务于模拟研究，不代表真实账户资金变化。
"""

from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_DOWN

from app.models.paper_trading_equity_snapshot import PaperTradingEquitySnapshot
from app.repositories.paper_trading_repo import AsyncPaperTradingRepository
from app.repositories.watchlist_repo import AsyncWatchlistRepository
from app.schemas.market import (
    MarketIndicatorResponse,
    MarketOverviewResponse,
    MarketQuoteResponse,
)
from app.schemas.market_data_sync import MarketDataQualityReport
from app.schemas.paper_trading import (
    PaperTradingAccountCreate,
    PaperTradingOrderSide,
    PaperTradingTickRequest,
)
from app.schemas.strategy_signal import StrategySignalResponse
from app.services.paper_trading_account_service import PaperTradingAccountService
from app.services.paper_trading_equity_service import PaperTradingEquityService
from app.services.paper_trading_order_service import (
    PaperTradingOrderExecutionItem,
    PaperTradingOrderExecutionResult,
    PaperTradingOrderService,
)
from app.services.paper_trading_position_service import PaperTradingPositionService
from app.services.paper_trading_signal_service import (
    PaperTradingSignalContext,
    PaperTradingSignalItem,
)


async def _create_account(
    db_session,
    user_id: int,
    initial_cash: Decimal = Decimal("100000"),
):
    account_service = PaperTradingAccountService(db_session)
    watchlist_item = await AsyncWatchlistRepository(db_session).create(
        user_id=user_id,
        symbol="AAPL",
        market="US",
        name="Apple",
    )

    response = await account_service.create_account(
        user_id=user_id,
        request=PaperTradingAccountCreate(
            name="量化专项纸面交易一致性账户",
            initial_cash=initial_cash,
            currency="CNY",
            watchlist_item_ids=[watchlist_item.id],
        ),
    )

    return await account_service.get_account_model(
        user_id=user_id,
        account_id=response.id,
    )


async def _refresh_account(db_session, user_id: int, account_id: int):
    return await PaperTradingAccountService(db_session).get_account_model(
        user_id=user_id,
        account_id=account_id,
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
            summary=f"{signal} signal for paper trading consistency test",
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


async def _execute_signals(
    db_session,
    *,
    account,
    user_id: int,
    items: list[PaperTradingSignalItem],
) -> PaperTradingOrderExecutionResult:
    return await PaperTradingOrderService(db_session).execute_signal_orders(
        account=account,
        signal_context=_signal_context(
            user_id=user_id,
            items=items,
        ),
    )


async def test_buy_trade_updates_cash_and_creates_position(db_session, test_user) -> None:
    account = await _create_account(db_session, user_id=test_user.id)

    execution_result = await _execute_signals(
        db_session,
        account=account,
        user_id=test_user.id,
        items=[
            _signal_item(
                symbol="PCASH",
                action="buy",
                latest_price=100,
            )
        ],
    )

    position_result = await PaperTradingPositionService(db_session).apply_execution_result(
        account=account,
        execution_result=execution_result,
    )

    assert position_result.account_id == account.id
    assert position_result.cash_before == Decimal("100000.0000")
    assert position_result.cash_after == Decimal("89997.0000")
    assert position_result.updated_position_count == 1
    assert position_result.warnings == []

    update_item = position_result.items[0]
    assert update_item.cash_before == Decimal("100000.0000")
    assert update_item.cash_after == Decimal("89997.0000")
    assert update_item.message == "买入成交已更新现金和持仓。"

    position = update_item.position
    assert position is not None
    assert position.symbol == "PCASH"
    assert position.quantity == Decimal("100.000000")
    assert position.avg_cost == Decimal("100.0300")
    assert position.last_price == Decimal("100.0000")
    assert position.market_value == Decimal("10000.0000")
    assert position.unrealized_pnl == Decimal("-3.0000")
    assert position.unrealized_return == Decimal("-0.00029991")

    refreshed_account = await _refresh_account(
        db_session,
        user_id=test_user.id,
        account_id=account.id,
    )
    assert refreshed_account.cash_balance == Decimal("89997.0000")


async def test_second_buy_trade_increases_position_and_recalculates_average_cost(
    db_session,
    test_user,
) -> None:
    account = await _create_account(db_session, user_id=test_user.id)
    position_service = PaperTradingPositionService(db_session)

    first_execution = await _execute_signals(
        db_session,
        account=account,
        user_id=test_user.id,
        items=[
            _signal_item(
                symbol="PADD",
                action="buy",
                latest_price=100,
            )
        ],
    )
    await position_service.apply_execution_result(
        account=account,
        execution_result=first_execution,
    )

    account_after_first_buy = await _refresh_account(
        db_session,
        user_id=test_user.id,
        account_id=account.id,
    )

    second_execution = await _execute_signals(
        db_session,
        account=account_after_first_buy,
        user_id=test_user.id,
        items=[
            _signal_item(
                symbol="PADD",
                action="buy",
                latest_price=120,
            )
        ],
    )
    second_position_result = await position_service.apply_execution_result(
        account=account_after_first_buy,
        execution_result=second_execution,
    )

    position = second_position_result.items[0].position
    assert position is not None

    expected_quantity = Decimal("174.997500")
    expected_total_cost = Decimal("10003.0000") + Decimal("9002.3999")
    expected_avg_cost = (expected_total_cost / expected_quantity).quantize(
        Decimal("0.0001"),
        rounding=ROUND_DOWN,
    )
    expected_market_value = Decimal("20999.7000")
    expected_cost_basis = (expected_quantity * expected_avg_cost).quantize(
        Decimal("0.0001"),
        rounding=ROUND_DOWN,
    )
    expected_unrealized_pnl = (expected_market_value - expected_cost_basis).quantize(
        Decimal("0.0001"),
        rounding=ROUND_DOWN,
    )

    assert second_position_result.cash_after == Decimal("80994.6001")
    assert position.quantity == expected_quantity
    assert position.avg_cost == expected_avg_cost
    assert position.last_price == Decimal("120.0000")
    assert position.market_value == expected_market_value
    assert position.unrealized_pnl == expected_unrealized_pnl
    assert position.unrealized_return is not None


async def test_sell_trade_updates_cash_and_zeroes_position_when_fully_sold(
    db_session,
    test_user,
) -> None:
    account = await _create_account(db_session, user_id=test_user.id)
    repository = AsyncPaperTradingRepository(db_session)

    await repository.create_position(
        account_id=account.id,
        symbol="PZERO",
        market="US",
        quantity=Decimal("12.500000"),
        avg_cost=Decimal("90.0000"),
        last_price=Decimal("100.0000"),
        market_value=Decimal("1250.0000"),
        unrealized_pnl=Decimal("125.0000"),
        unrealized_return=Decimal("0.10000000"),
    )

    execution_result = await _execute_signals(
        db_session,
        account=account,
        user_id=test_user.id,
        items=[
            _signal_item(
                symbol="PZERO",
                action="sell",
                latest_price=110,
            )
        ],
    )

    position_result = await PaperTradingPositionService(db_session).apply_execution_result(
        account=account,
        execution_result=execution_result,
    )

    assert position_result.cash_before == Decimal("100000.0000")
    assert position_result.cash_after == Decimal("101374.5875")

    position = position_result.items[0].position
    assert position is not None
    assert position.quantity == Decimal("0.000000")
    assert position.avg_cost == Decimal("0.0000")
    assert position.last_price == Decimal("110.0000")
    assert position.market_value == Decimal("0.0000")
    assert position.unrealized_pnl == Decimal("0.0000")
    assert position.unrealized_return is None


async def test_partial_sell_trade_reduces_position_and_keeps_remaining_market_value(
    db_session,
    test_user,
) -> None:
    account = await _create_account(db_session, user_id=test_user.id)
    repository = AsyncPaperTradingRepository(db_session)

    await repository.create_position(
        account_id=account.id,
        symbol="PPART",
        market="US",
        quantity=Decimal("10.000000"),
        avg_cost=Decimal("90.0000"),
        last_price=Decimal("100.0000"),
        market_value=Decimal("1000.0000"),
        unrealized_pnl=Decimal("100.0000"),
        unrealized_return=Decimal("0.11111111"),
    )

    trade = await repository.create_trade(
        account_id=account.id,
        order_id=None,
        symbol="PPART",
        market="US",
        side=PaperTradingOrderSide.SELL,
        filled_quantity=Decimal("4.000000"),
        filled_price=Decimal("110.0000"),
        trade_value=Decimal("440.0000"),
        fee_amount=Decimal("0.1320"),
        traded_at=datetime.now(UTC),
    )

    execution_result = PaperTradingOrderExecutionResult(
        account_id=account.id,
        signal_count=1,
        order_count=0,
        trade_count=1,
        items=[
            PaperTradingOrderExecutionItem(
                symbol="PPART",
                market="US",
                action="sell",
                trade=trade,
                status="filled",
            )
        ],
    )

    position_result = await PaperTradingPositionService(db_session).apply_execution_result(
        account=account,
        execution_result=execution_result,
    )

    assert position_result.cash_after == Decimal("100439.8680")

    position = position_result.items[0].position
    assert position is not None
    assert position.quantity == Decimal("6.000000")
    assert position.avg_cost == Decimal("90.0000")
    assert position.last_price == Decimal("110.0000")
    assert position.market_value == Decimal("660.0000")
    assert position.unrealized_pnl == Decimal("120.0000")
    assert position.unrealized_return == Decimal("0.22222222")


async def test_equity_snapshot_uses_updated_cash_and_position_market_value(
    db_session,
    test_user,
) -> None:
    account = await _create_account(db_session, user_id=test_user.id)

    execution_result = await _execute_signals(
        db_session,
        account=account,
        user_id=test_user.id,
        items=[
            _signal_item(
                symbol="PEQ",
                action="buy",
                latest_price=100,
            )
        ],
    )

    await PaperTradingPositionService(db_session).apply_execution_result(
        account=account,
        execution_result=execution_result,
    )

    updated_account = await _refresh_account(
        db_session,
        user_id=test_user.id,
        account_id=account.id,
    )

    equity_result = await PaperTradingEquityService(db_session).create_or_update_snapshot(
        account=updated_account,
        user_id=test_user.id,
        snapshot_date=date(2026, 1, 2),
    )

    assert equity_result.created is True
    assert equity_result.calculation.cash_balance == Decimal("89997.0000")
    assert equity_result.calculation.position_market_value == Decimal("10000.0000")
    assert equity_result.calculation.total_equity == Decimal("99997.0000")
    assert equity_result.calculation.total_return == Decimal("-0.00003000")
    assert equity_result.calculation.daily_return is None
    assert equity_result.calculation.max_drawdown == Decimal("0.00000000")
    assert equity_result.calculation.position_count == 1

    snapshot = equity_result.snapshot
    assert snapshot.cash_balance == Decimal("89997.0000")
    assert snapshot.position_market_value == Decimal("10000.0000")
    assert snapshot.total_equity == Decimal("99997.0000")
    assert snapshot.total_return == Decimal("-0.00003000")


async def test_equity_snapshot_updates_same_account_same_date_instead_of_creating_duplicate(
    db_session,
    test_user,
) -> None:
    account = await _create_account(db_session, user_id=test_user.id)

    equity_service = PaperTradingEquityService(db_session)
    snapshot_date = date(2026, 1, 3)

    first_result = await equity_service.create_or_update_snapshot(
        account=account,
        user_id=test_user.id,
        snapshot_date=snapshot_date,
    )

    second_result = await equity_service.create_or_update_snapshot(
        account=account,
        user_id=test_user.id,
        snapshot_date=snapshot_date,
    )

    assert first_result.created is True
    assert second_result.created is False
    assert second_result.snapshot.id == first_result.snapshot.id


async def test_equity_snapshot_calculates_daily_return_and_max_drawdown(
    db_session,
    test_user,
) -> None:
    account = await _create_account(db_session, user_id=test_user.id)
    repository = AsyncPaperTradingRepository(db_session)

    await repository.create_equity_snapshot(
        account_id=account.id,
        snapshot_date=date(2026, 1, 1),
        cash_balance=Decimal("100000.0000"),
        position_market_value=Decimal("0.0000"),
        total_equity=Decimal("100000.0000"),
        total_return=Decimal("0.00000000"),
        daily_return=None,
        max_drawdown=Decimal("0.00000000"),
    )

    updated_account = await repository.update_account_cash(
        account=account,
        cash_balance=Decimal("90000.0000"),
    )

    equity_result = await PaperTradingEquityService(db_session).create_or_update_snapshot(
        account=updated_account,
        user_id=test_user.id,
        snapshot_date=date(2026, 1, 2),
    )

    assert equity_result.created is True
    assert equity_result.calculation.cash_balance == Decimal("90000.0000")
    assert equity_result.calculation.position_market_value == Decimal("0.0000")
    assert equity_result.calculation.total_equity == Decimal("90000.0000")
    assert equity_result.calculation.total_return == Decimal("-0.10000000")
    assert equity_result.calculation.daily_return == Decimal("-0.10000000")
    assert equity_result.calculation.max_drawdown == Decimal("0.10000000")

    latest_response = await PaperTradingEquityService(db_session).get_latest_snapshot(
        account_id=account.id,
        user_id=test_user.id,
    )
    assert latest_response is not None
    assert latest_response.snapshot_date == date(2026, 1, 2)
