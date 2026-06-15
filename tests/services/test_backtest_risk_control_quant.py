"""回测风控规则专项测试。

验证手续费、滑点、止损、止盈、冷却期和最大回撤保护。
这些规则只作用于历史模拟回测，不连接券商、不真实下单。
"""

from decimal import Decimal

import pytest

from app.schemas.backtest import (
    BacktestRequest,
    BacktestRiskControlConfig,
    BacktestSignalSnapshot,
    BacktestTrade,
)
from app.services.backtest_service import BacktestService
from tests.fixtures.quant_data import build_candle_payload, build_uptrend_candles


def _backtest_request(
    candles,
    *,
    risk_control: BacktestRiskControlConfig | None = None,
    initial_cash: Decimal = Decimal("100000"),
    position_size_ratio: float = 1.0,
) -> BacktestRequest:
    return BacktestRequest(
        symbol=candles[0].symbol,
        market="US",
        start_date=candles[0].candle_time.date(),
        end_date=candles[-1].candle_time.date(),
        timeframe="1d",
        initial_cash=initial_cash,
        position_size_ratio=position_size_ratio,
        risk_control=risk_control or BacktestRiskControlConfig(),
        adjust_type="none",
        source="mock",
        min_required_candles=35,
        enforce_data_quality=False,
        data_quality_stale_after_days=None,
        include_trades=True,
        include_daily_equity=True,
        include_signal_snapshots=True,
    )


def _snapshot(
    candle,
    *,
    decision: str,
    signal: str | None = None,
    score: int | None = None,
) -> BacktestSignalSnapshot:
    return BacktestSignalSnapshot(
        trade_date=candle.candle_time.date(),
        decision=decision,
        signal=signal,
        signal_strength="strong" if signal in {"buy", "sell"} else None,
        signal_score=score,
        close_price=candle.close_price,
        reason="manual signal for risk control test",
        warnings=[],
    )


def _buy_trade(
    *,
    trade_date,
    price: Decimal = Decimal("100"),
    quantity: int = 100,
    commission: Decimal = Decimal("0"),
) -> BacktestTrade:
    trade_value = price * Decimal(quantity)

    return BacktestTrade(
        sequence_no=1,
        action="buy",
        trade_date=trade_date,
        price=price,
        quantity=quantity,
        raw_price=price,
        slippage_amount=Decimal("0"),
        slippage_rate=0.0,
        commission=commission,
        commission_rate=0.0,
        risk_rule=None,
        signal_date=trade_date,
        execution_price_type="next_open",
        trade_value=trade_value,
        cash_before=Decimal("100000"),
        cash_after=Decimal("100000") - trade_value - commission,
        position_before=0,
        position_after=quantity,
        equity_after=Decimal("100000"),
        realized_pnl=None,
        realized_return=None,
        holding_days=None,
        signal="buy",
        signal_strength="strong",
        signal_score=90,
        reason="manual open buy trade",
    )


def test_calculate_commission_uses_rate_and_minimum_commission() -> None:
    service = BacktestService(None)

    assert service._calculate_commission(
        trade_value=Decimal("10000"),
        commission_rate=0.001,
        min_commission=Decimal("0"),
    ) == Decimal("10.000")

    assert service._calculate_commission(
        trade_value=Decimal("1000"),
        commission_rate=0.001,
        min_commission=Decimal("5"),
    ) == Decimal("5")

    assert service._calculate_commission(
        trade_value=Decimal("1000"),
        commission_rate=0.0,
        min_commission=Decimal("5"),
    ) == Decimal("0")


def test_apply_slippage_adjusts_buy_and_sell_execution_price() -> None:
    service = BacktestService(None)

    buy_price, buy_slippage, buy_price_type = service._apply_slippage(
        raw_price=Decimal("100"),
        action="buy",
        slippage_rate=0.01,
    )
    sell_price, sell_slippage, sell_price_type = service._apply_slippage(
        raw_price=Decimal("100"),
        action="sell",
        slippage_rate=0.01,
    )
    flat_price, flat_slippage, flat_price_type = service._apply_slippage(
        raw_price=Decimal("100"),
        action="buy",
        slippage_rate=0.0,
    )

    assert buy_price == Decimal("101.00")
    assert buy_slippage == Decimal("1.00")
    assert buy_price_type == "next_open_with_slippage"

    assert sell_price == Decimal("99.00")
    assert sell_slippage == Decimal("1.00")
    assert sell_price_type == "next_open_with_slippage"

    assert flat_price == Decimal("100")
    assert flat_slippage == Decimal("0")
    assert flat_price_type == "next_open"


def test_stop_loss_decision_changes_snapshot_when_close_price_reaches_threshold() -> None:
    candles = build_uptrend_candles(symbol="BTSL", count=3)
    request = _backtest_request(
        candles,
        risk_control=BacktestRiskControlConfig(
            enable_stop_loss=True,
            stop_loss_rate=0.1,
        ),
    )
    open_buy_trade = _buy_trade(
        trade_date=candles[0].candle_time.date(),
        price=Decimal("100"),
    )
    snapshot = _snapshot(
        candles[1].model_copy(update={"close_price": Decimal("90")}),
        decision="hold",
    )

    result = BacktestService(None)._apply_stop_loss_decision(
        request=request,
        snapshot=snapshot,
        position_quantity=100,
        open_buy_trade=open_buy_trade,
    )

    assert result.decision == "stop_loss"
    assert result.risk_rule == "stop_loss"
    assert result.risk_triggered is True
    assert result.close_price == Decimal("90")


def test_stop_loss_decision_keeps_snapshot_when_rule_disabled_or_not_triggered() -> None:
    candles = build_uptrend_candles(symbol="BTSLNO", count=3)
    service = BacktestService(None)
    open_buy_trade = _buy_trade(
        trade_date=candles[0].candle_time.date(),
        price=Decimal("100"),
    )
    snapshot = _snapshot(
        candles[1].model_copy(update={"close_price": Decimal("95")}),
        decision="hold",
    )

    disabled_request = _backtest_request(
        candles,
        risk_control=BacktestRiskControlConfig(
            enable_stop_loss=False,
            stop_loss_rate=0.1,
        ),
    )
    enabled_request = _backtest_request(
        candles,
        risk_control=BacktestRiskControlConfig(
            enable_stop_loss=True,
            stop_loss_rate=0.1,
        ),
    )

    disabled_result = service._apply_stop_loss_decision(
        request=disabled_request,
        snapshot=snapshot,
        position_quantity=100,
        open_buy_trade=open_buy_trade,
    )
    not_triggered_result = service._apply_stop_loss_decision(
        request=enabled_request,
        snapshot=snapshot,
        position_quantity=100,
        open_buy_trade=open_buy_trade,
    )

    assert disabled_result.decision == "hold"
    assert not_triggered_result.decision == "hold"


def test_take_profit_decision_changes_snapshot_when_close_price_reaches_threshold() -> None:
    candles = build_uptrend_candles(symbol="BTTP", count=3)
    request = _backtest_request(
        candles,
        risk_control=BacktestRiskControlConfig(
            enable_take_profit=True,
            take_profit_rate=0.2,
        ),
    )
    open_buy_trade = _buy_trade(
        trade_date=candles[0].candle_time.date(),
        price=Decimal("100"),
    )
    snapshot = _snapshot(
        candles[1].model_copy(update={"close_price": Decimal("120")}),
        decision="hold",
    )

    result = BacktestService(None)._apply_take_profit_decision(
        request=request,
        snapshot=snapshot,
        position_quantity=100,
        open_buy_trade=open_buy_trade,
    )

    assert result.decision == "take_profit"
    assert result.risk_rule == "take_profit"
    assert result.risk_triggered is True
    assert result.close_price == Decimal("120")


def test_take_profit_does_not_override_stop_loss_decision() -> None:
    candles = build_uptrend_candles(symbol="BTTPNO", count=3)
    request = _backtest_request(
        candles,
        risk_control=BacktestRiskControlConfig(
            enable_take_profit=True,
            take_profit_rate=0.2,
        ),
    )
    open_buy_trade = _buy_trade(
        trade_date=candles[0].candle_time.date(),
        price=Decimal("100"),
    )
    snapshot = _snapshot(
        candles[1].model_copy(update={"close_price": Decimal("130")}),
        decision="stop_loss",
    )

    result = BacktestService(None)._apply_take_profit_decision(
        request=request,
        snapshot=snapshot,
        position_quantity=100,
        open_buy_trade=open_buy_trade,
    )

    assert result.decision == "stop_loss"


def test_drawdown_guard_changes_buy_signal_when_account_drawdown_reaches_threshold() -> None:
    candles = build_uptrend_candles(symbol="BTDD", count=3)
    request = _backtest_request(
        candles,
        risk_control=BacktestRiskControlConfig(
            enable_max_drawdown_guard=True,
            max_drawdown_guard_rate=0.05,
        ),
    )
    snapshot = _snapshot(candles[1], decision="buy", signal="buy", score=90)

    result = BacktestService(None)._apply_drawdown_guard_decision(
        request=request,
        snapshot=snapshot,
        position_quantity=0,
        current_drawdown=0.06,
    )

    assert result.decision == "drawdown_guard"
    assert result.risk_rule == "drawdown_guard"
    assert result.risk_triggered is True
    assert result.current_drawdown == pytest.approx(0.06)


def test_drawdown_guard_keeps_signal_when_holding_position_or_below_threshold() -> None:
    candles = build_uptrend_candles(symbol="BTDDNO", count=3)
    request = _backtest_request(
        candles,
        risk_control=BacktestRiskControlConfig(
            enable_max_drawdown_guard=True,
            max_drawdown_guard_rate=0.05,
        ),
    )
    snapshot = _snapshot(candles[1], decision="buy", signal="buy", score=90)
    service = BacktestService(None)

    holding_result = service._apply_drawdown_guard_decision(
        request=request,
        snapshot=snapshot,
        position_quantity=100,
        current_drawdown=0.06,
    )
    below_threshold_result = service._apply_drawdown_guard_decision(
        request=request,
        snapshot=snapshot,
        position_quantity=0,
        current_drawdown=0.04,
    )

    assert holding_result.decision == "buy"
    assert holding_result.current_drawdown == pytest.approx(0.06)
    assert below_threshold_result.decision == "buy"
    assert below_threshold_result.current_drawdown == pytest.approx(0.04)


def test_cooldown_decision_changes_buy_signal_when_cooldown_days_left() -> None:
    candles = build_uptrend_candles(symbol="BTCD", count=3)
    request = _backtest_request(
        candles,
        risk_control=BacktestRiskControlConfig(
            enable_cooldown=True,
            cooldown_days=2,
        ),
    )
    snapshot = _snapshot(candles[1], decision="buy", signal="buy", score=90)

    result = BacktestService(None)._apply_cooldown_decision(
        request=request,
        snapshot=snapshot,
        position_quantity=0,
        cooldown_days_left=2,
    )

    assert result.decision == "cooldown"
    assert result.risk_rule == "cooldown"
    assert result.risk_triggered is True
    assert result.cooldown_days_left == 2


def test_cooldown_decision_does_not_override_drawdown_guard() -> None:
    candles = build_uptrend_candles(symbol="BTCDNO", count=3)
    request = _backtest_request(
        candles,
        risk_control=BacktestRiskControlConfig(
            enable_cooldown=True,
            cooldown_days=2,
        ),
    )
    snapshot = _snapshot(candles[1], decision="drawdown_guard")

    result = BacktestService(None)._apply_cooldown_decision(
        request=request,
        snapshot=snapshot,
        position_quantity=0,
        cooldown_days_left=2,
    )

    assert result.decision == "drawdown_guard"


def test_match_trades_applies_commission_and_slippage_to_buy_trade() -> None:
    candles = build_uptrend_candles(symbol="BTCBUY", count=3)
    request = _backtest_request(
        candles,
        risk_control=BacktestRiskControlConfig(
            commission_rate=0.001,
            min_commission=Decimal("5"),
            slippage_rate=0.01,
        ),
    )
    snapshots = [
        _snapshot(candles[0], decision="buy", signal="buy", score=90),
        _snapshot(candles[1], decision="hold"),
        _snapshot(candles[2], decision="hold"),
    ]

    trades = BacktestService(None)._match_trades(
        request=request,
        candles=candles,
        signal_snapshots=snapshots,
    )

    assert len(trades) == 1

    buy_trade = trades[0]
    assert buy_trade.action == "buy"
    assert buy_trade.raw_price == candles[1].open_price
    assert buy_trade.price == candles[1].open_price * Decimal("1.01")
    assert buy_trade.slippage_amount == buy_trade.price - candles[1].open_price
    assert buy_trade.execution_price_type == "next_open_with_slippage"

    assert buy_trade.trade_value == buy_trade.price * Decimal(buy_trade.quantity)
    assert buy_trade.commission >= Decimal("5")
    assert buy_trade.cash_after == (
        buy_trade.cash_before - buy_trade.trade_value - buy_trade.commission
    )


def test_match_trades_applies_stop_loss_sell_and_records_realized_loss() -> None:
    candles = build_uptrend_candles(symbol="BTFULLSL", count=4)
    candles[2] = candles[2].model_copy(
        update={
            "open_price": Decimal("90.0000"),
            "high_price": Decimal("91.0000"),
            "low_price": Decimal("88.0000"),
            "close_price": Decimal("89.0000"),
        }
    )
    candles[3] = candles[3].model_copy(
        update={
            "open_price": Decimal("88.0000"),
            "high_price": Decimal("89.0000"),
            "low_price": Decimal("87.0000"),
            "close_price": Decimal("88.0000"),
        }
    )

    request = _backtest_request(
        candles,
        risk_control=BacktestRiskControlConfig(
            enable_stop_loss=True,
            stop_loss_rate=0.1,
        ),
    )
    snapshots = [
        _snapshot(candles[0], decision="buy", signal="buy", score=90),
        _snapshot(candles[1], decision="hold"),
        _snapshot(candles[2], decision="hold"),
        _snapshot(candles[3], decision="hold"),
    ]

    trades = BacktestService(None)._match_trades(
        request=request,
        candles=candles,
        signal_snapshots=snapshots,
    )

    assert len(trades) == 2
    assert snapshots[2].decision == "stop_loss"

    sell_trade = trades[1]
    assert sell_trade.action == "sell"
    assert sell_trade.risk_rule == "stop_loss"
    assert sell_trade.realized_pnl is not None
    assert sell_trade.realized_pnl < 0
    assert sell_trade.holding_days == (
        sell_trade.trade_date - trades[0].trade_date
    ).days


def test_match_trades_applies_take_profit_sell_and_records_realized_profit() -> None:
    candles = build_uptrend_candles(symbol="BTFULLTP", count=4)
    candles[2] = candles[2].model_copy(
        update={
            "open_price": Decimal("125.0000"),
            "high_price": Decimal("126.0000"),
            "low_price": Decimal("124.0000"),
            "close_price": Decimal("125.0000"),
        }
    )
    candles[3] = candles[3].model_copy(
        update={
            "open_price": Decimal("126.0000"),
            "high_price": Decimal("127.0000"),
            "low_price": Decimal("125.0000"),
            "close_price": Decimal("126.0000"),
        }
    )

    request = _backtest_request(
        candles,
        risk_control=BacktestRiskControlConfig(
            enable_take_profit=True,
            take_profit_rate=0.2,
        ),
    )
    snapshots = [
        _snapshot(candles[0], decision="buy", signal="buy", score=90),
        _snapshot(candles[1], decision="hold"),
        _snapshot(candles[2], decision="hold"),
        _snapshot(candles[3], decision="hold"),
    ]

    trades = BacktestService(None)._match_trades(
        request=request,
        candles=candles,
        signal_snapshots=snapshots,
    )

    assert len(trades) == 2
    assert snapshots[2].decision == "take_profit"

    sell_trade = trades[1]
    assert sell_trade.action == "sell"
    assert sell_trade.risk_rule == "take_profit"
    assert sell_trade.realized_pnl is not None
    assert sell_trade.realized_pnl > 0


def test_match_trades_applies_drawdown_guard_before_buying() -> None:
    candles = build_uptrend_candles(symbol="BTFULLDD", count=4)
    request = _backtest_request(
        candles,
        initial_cash=Decimal("100000"),
        risk_control=BacktestRiskControlConfig(
            enable_max_drawdown_guard=True,
            max_drawdown_guard_rate=0.05,
        ),
    )
    snapshots = [
        _snapshot(candles[0], decision="buy", signal="buy", score=90),
        _snapshot(candles[1], decision="hold"),
        _snapshot(candles[2], decision="buy", signal="buy", score=90),
        _snapshot(candles[3], decision="hold"),
    ]

    buy_trade = _buy_trade(
        trade_date=candles[1].candle_time.date(),
        price=candles[1].open_price,
        quantity=900,
    )
    trades = [buy_trade]
    daily_equity = BacktestService(None)._build_daily_equity(
        request=request,
        candles=[
            candles[0],
            candles[1],
            candles[2].model_copy(update={"close_price": Decimal("90.0000")}),
            candles[3],
        ],
        trades=trades,
    )

    current_drawdown = daily_equity[2].drawdown
    result = BacktestService(None)._apply_drawdown_guard_decision(
        request=request,
        snapshot=snapshots[2],
        position_quantity=0,
        current_drawdown=current_drawdown,
    )

    assert current_drawdown >= 0.05
    assert result.decision == "drawdown_guard"
    assert result.risk_rule == "drawdown_guard"


def test_build_metrics_counts_risk_control_results_from_trades_and_snapshots() -> None:
    candles = build_uptrend_candles(symbol="BTMETRISK", count=4)
    request = _backtest_request(candles)

    trades = [
        _buy_trade(
            trade_date=candles[0].candle_time.date(),
            price=Decimal("100"),
            quantity=10,
        ),
        _buy_trade(
            trade_date=candles[1].candle_time.date(),
            price=Decimal("100"),
            quantity=10,
        ).model_copy(
            update={
                "sequence_no": 2,
                "action": "sell",
                "risk_rule": "stop_loss",
                "realized_pnl": Decimal("-100"),
                "realized_return": -0.1,
            }
        ),
        _buy_trade(
            trade_date=candles[2].candle_time.date(),
            price=Decimal("100"),
            quantity=10,
        ).model_copy(
            update={
                "sequence_no": 3,
                "action": "sell",
                "risk_rule": "take_profit",
                "realized_pnl": Decimal("200"),
                "realized_return": 0.2,
            }
        ),
    ]
    daily_equity = BacktestService(None)._build_daily_equity(
        request=request,
        candles=candles,
        trades=[],
    )
    signal_snapshots = [
        _snapshot(candles[0], decision="buy", signal="buy", score=90),
        _snapshot(candles[1], decision="cooldown"),
        _snapshot(candles[2], decision="drawdown_guard"),
        _snapshot(candles[3], decision="hold"),
    ]

    metrics = BacktestService(None)._build_metrics(
        request=request,
        candles=candles,
        trades=trades,
        daily_equity=daily_equity,
        signal_snapshots=signal_snapshots,
    )

    assert metrics.stop_loss_trigger_count == 1
    assert metrics.take_profit_trigger_count == 1
    assert metrics.cooldown_skip_count == 1
    assert metrics.drawdown_guard_trigger_count == 1
