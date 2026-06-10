import math
from decimal import Decimal

import pytest

from app.schemas.backtest import (
    BacktestDailyEquity,
    BacktestInputSnapshot,
    BacktestRequest,
    BacktestSignalSnapshot,
    BacktestTrade,
)
from app.services.backtest_data_service import BacktestCandleData
from app.services.backtest_service import BacktestService
from tests.fixtures.quant_data import build_uptrend_candles


class FakeBacktestDataService:
    def __init__(self, candles) -> None:
        self.candles = candles

    async def get_candles_for_backtest(
        self,
        request: BacktestRequest,
    ) -> BacktestCandleData:
        return BacktestCandleData(
            candles=self.candles,
            input_snapshot=BacktestInputSnapshot(
                candle_count=len(self.candles),
                first_candle_date=self.candles[0].candle_time.date(),
                last_candle_date=self.candles[-1].candle_time.date(),
                strategy_name="strategy_signal_v1",
                timeframe=request.timeframe,
                adjust_type=request.adjust_type,
                source=request.source,
                min_required_candles=request.min_required_candles,
                position_size_ratio=request.position_size_ratio,
                risk_control=request.risk_control,
            ),
            warnings=[],
        )


def _backtest_request(
    candles,
    *,
    initial_cash: Decimal = Decimal("100000"),
) -> BacktestRequest:
    return BacktestRequest(
        symbol=candles[0].symbol,
        market="US",
        start_date=candles[0].candle_time.date(),
        end_date=candles[-1].candle_time.date(),
        timeframe="1d",
        initial_cash=initial_cash,
        position_size_ratio=1.0,
        adjust_type="none",
        source="mock",
        min_required_candles=35,
        enforce_data_quality=False,
        data_quality_stale_after_days=None,
        include_trades=True,
        include_daily_equity=True,
        include_signal_snapshots=True,
    )


def _daily_equity_from_totals(
    candles,
    totals: list[Decimal],
) -> list[BacktestDailyEquity]:
    result: list[BacktestDailyEquity] = []
    previous_equity: Decimal | None = None
    peak_equity = totals[0]

    for candle, total_equity in zip(candles, totals, strict=True):
        if total_equity > peak_equity:
            peak_equity = total_equity

        if previous_equity is None:
            daily_return = None
        else:
            daily_return = float((total_equity - previous_equity) / previous_equity)

        drawdown = 0.0
        if peak_equity > 0:
            drawdown = float((peak_equity - total_equity) / peak_equity)

        result.append(
            BacktestDailyEquity(
                trade_date=candle.candle_time.date(),
                close_price=candle.close_price,
                cash=total_equity,
                position_quantity=0,
                position_market_value=Decimal("0"),
                total_equity=total_equity,
                daily_return=daily_return,
                drawdown=drawdown,
            )
        )

        previous_equity = total_equity

    return result


def _trade(
    *,
    sequence_no: int,
    action: str,
    trade_date,
    price: Decimal,
    quantity: int,
    trade_value: Decimal,
    commission: Decimal = Decimal("0"),
    slippage_amount: Decimal = Decimal("0"),
    risk_rule: str | None = None,
    realized_pnl: Decimal | None = None,
    realized_return: float | None = None,
    holding_days: int | None = None,
) -> BacktestTrade:
    if action == "buy":
        position_before = 0
        position_after = quantity
        signal = "buy"
    else:
        position_before = quantity
        position_after = 0
        signal = "sell"

    return BacktestTrade(
        sequence_no=sequence_no,
        action=action,
        trade_date=trade_date,
        price=price,
        quantity=quantity,
        raw_price=price,
        slippage_amount=slippage_amount,
        slippage_rate=0.0,
        commission=commission,
        commission_rate=0.0,
        risk_rule=risk_rule,
        signal_date=trade_date,
        execution_price_type="next_open",
        trade_value=trade_value,
        cash_before=Decimal("100000"),
        cash_after=Decimal("100000"),
        position_before=position_before,
        position_after=position_after,
        equity_after=Decimal("100000"),
        realized_pnl=realized_pnl,
        realized_return=realized_return,
        holding_days=holding_days,
        signal=signal,
        signal_strength="strong",
        signal_score=80,
        reason="manual trade for performance metrics test",
    )


def _signal_snapshot(
    *,
    candle,
    decision: str,
) -> BacktestSignalSnapshot:
    return BacktestSignalSnapshot(
        trade_date=candle.candle_time.date(),
        decision=decision,
        signal=None,
        signal_strength=None,
        signal_score=None,
        risk_rule=decision if decision in {"cooldown", "drawdown_guard"} else None,
        risk_triggered=decision in {"cooldown", "drawdown_guard"},
        cooldown_days_left=1 if decision == "cooldown" else None,
        current_drawdown=0.1 if decision == "drawdown_guard" else None,
        close_price=candle.close_price,
        reason="manual signal snapshot for performance metrics test",
        warnings=[],
    )


def test_build_metrics_calculates_return_risk_and_benchmark_fields() -> None:
    candles = build_uptrend_candles(symbol="BTPERF", count=4)
    request = _backtest_request(candles)

    totals = [
        Decimal("100000"),
        Decimal("102000"),
        Decimal("101000"),
        Decimal("105000"),
    ]
    daily_equity = _daily_equity_from_totals(candles, totals)

    service = BacktestService(None)
    metrics = service._build_metrics(
        request=request,
        candles=candles,
        trades=[],
        daily_equity=daily_equity,
        signal_snapshots=[],
    )

    daily_returns = [
        item.daily_return
        for item in daily_equity
        if item.daily_return is not None
    ]
    average_daily_return = sum(daily_returns) / len(daily_returns)
    variance = sum(
        (daily_return - average_daily_return) ** 2
        for daily_return in daily_returns
    ) / (len(daily_returns) - 1)
    daily_return_volatility = math.sqrt(variance)

    expected_total_return = 0.05
    expected_annualized_return = float(
        Decimal("105000") / Decimal("100000")
    ) ** (252 / len(daily_equity)) - 1
    expected_max_drawdown = max(item.drawdown for item in daily_equity)

    assert metrics.initial_cash == Decimal("100000")
    assert metrics.final_equity == Decimal("105000")
    assert metrics.total_return == pytest.approx(expected_total_return)
    assert metrics.annualized_return == pytest.approx(expected_annualized_return)
    assert metrics.average_daily_return == pytest.approx(average_daily_return)

    assert metrics.max_drawdown == pytest.approx(expected_max_drawdown)
    assert metrics.daily_return_volatility == pytest.approx(daily_return_volatility)
    assert metrics.annualized_volatility == pytest.approx(
        daily_return_volatility * math.sqrt(252)
    )
    assert metrics.sharpe_ratio == pytest.approx(
        average_daily_return / daily_return_volatility * math.sqrt(252)
    )
    assert metrics.return_drawdown_ratio == pytest.approx(
        expected_total_return / expected_max_drawdown
    )

    assert metrics.buy_and_hold_return == pytest.approx(0.03)
    assert metrics.excess_return == pytest.approx(0.02)
    assert metrics.outperformed_buy_and_hold is True


def test_build_metrics_calculates_completed_trade_performance_fields() -> None:
    candles = build_uptrend_candles(symbol="BTTRD", count=4)
    request = _backtest_request(candles)

    daily_equity = _daily_equity_from_totals(
        candles,
        [
            Decimal("100000"),
            Decimal("100200"),
            Decimal("100100"),
            Decimal("100100"),
        ],
    )
    trades = [
        _trade(
            sequence_no=1,
            action="buy",
            trade_date=candles[0].candle_time.date(),
            price=Decimal("100"),
            quantity=10,
            trade_value=Decimal("1000"),
        ),
        _trade(
            sequence_no=2,
            action="sell",
            trade_date=candles[1].candle_time.date(),
            price=Decimal("120"),
            quantity=10,
            trade_value=Decimal("1200"),
            realized_pnl=Decimal("200"),
            realized_return=0.2,
            holding_days=2,
        ),
        _trade(
            sequence_no=3,
            action="buy",
            trade_date=candles[2].candle_time.date(),
            price=Decimal("100"),
            quantity=10,
            trade_value=Decimal("1000"),
        ),
        _trade(
            sequence_no=4,
            action="sell",
            trade_date=candles[3].candle_time.date(),
            price=Decimal("90"),
            quantity=10,
            trade_value=Decimal("900"),
            realized_pnl=Decimal("-100"),
            realized_return=-0.1,
            holding_days=3,
        ),
    ]

    metrics = BacktestService(None)._build_metrics(
        request=request,
        candles=candles,
        trades=trades,
        daily_equity=daily_equity,
        signal_snapshots=[],
    )

    assert metrics.trade_count == 4
    assert metrics.buy_count == 2
    assert metrics.sell_count == 2

    assert metrics.completed_trade_count == 2
    assert metrics.winning_trade_count == 1
    assert metrics.losing_trade_count == 1
    assert metrics.win_rate == pytest.approx(0.5)

    assert metrics.average_win == Decimal("200")
    assert metrics.average_loss == Decimal("-100")
    assert metrics.profit_loss_ratio == pytest.approx(2.0)
    assert metrics.average_realized_return == pytest.approx(0.05)

    assert metrics.best_trade_pnl == Decimal("200")
    assert metrics.worst_trade_pnl == Decimal("-100")
    assert metrics.average_holding_days == pytest.approx(2.5)


def test_build_metrics_counts_commission_slippage_and_risk_decisions() -> None:
    candles = build_uptrend_candles(symbol="BTCOST", count=4)
    request = _backtest_request(candles)

    daily_equity = _daily_equity_from_totals(
        candles,
        [
            Decimal("100000"),
            Decimal("100050"),
            Decimal("99900"),
            Decimal("100300"),
        ],
    )
    trades = [
        _trade(
            sequence_no=1,
            action="buy",
            trade_date=candles[0].candle_time.date(),
            price=Decimal("100"),
            quantity=10,
            trade_value=Decimal("1000"),
            commission=Decimal("1"),
            slippage_amount=Decimal("0.10"),
        ),
        _trade(
            sequence_no=2,
            action="sell",
            trade_date=candles[1].candle_time.date(),
            price=Decimal("98"),
            quantity=10,
            trade_value=Decimal("980"),
            commission=Decimal("2"),
            slippage_amount=Decimal("0.20"),
            risk_rule="stop_loss",
            realized_pnl=Decimal("-22"),
            realized_return=-0.022,
            holding_days=1,
        ),
        _trade(
            sequence_no=3,
            action="buy",
            trade_date=candles[2].candle_time.date(),
            price=Decimal("100"),
            quantity=5,
            trade_value=Decimal("500"),
            commission=Decimal("1"),
            slippage_amount=Decimal("0.05"),
        ),
        _trade(
            sequence_no=4,
            action="sell",
            trade_date=candles[3].candle_time.date(),
            price=Decimal("110"),
            quantity=5,
            trade_value=Decimal("550"),
            commission=Decimal("2"),
            slippage_amount=Decimal("0.30"),
            risk_rule="take_profit",
            realized_pnl=Decimal("47"),
            realized_return=0.094,
            holding_days=1,
        ),
    ]
    signal_snapshots = [
        _signal_snapshot(candle=candles[0], decision="buy"),
        _signal_snapshot(candle=candles[1], decision="cooldown"),
        _signal_snapshot(candle=candles[2], decision="drawdown_guard"),
        _signal_snapshot(candle=candles[3], decision="hold"),
    ]

    metrics = BacktestService(None)._build_metrics(
        request=request,
        candles=candles,
        trades=trades,
        daily_equity=daily_equity,
        signal_snapshots=signal_snapshots,
    )

    assert metrics.total_commission == Decimal("6")
    assert metrics.total_slippage_cost == Decimal("4.75")

    assert metrics.stop_loss_trigger_count == 1
    assert metrics.take_profit_trigger_count == 1
    assert metrics.cooldown_skip_count == 1
    assert metrics.drawdown_guard_trigger_count == 1


def test_metric_helper_methods_return_none_for_unavailable_edge_cases() -> None:
    service = BacktestService(None)

    assert service._calculate_annualized_return(
        initial_cash=Decimal("100000"),
        final_equity=Decimal("101000"),
        trading_days=0,
    ) is None

    assert service._calculate_daily_return_volatility([0.01]) is None
    assert service._calculate_annualized_volatility(None) is None

    assert service._calculate_sharpe_ratio(
        average_daily_return=None,
        daily_return_volatility=0.01,
    ) is None
    assert service._calculate_sharpe_ratio(
        average_daily_return=0.01,
        daily_return_volatility=0,
    ) is None

    assert service._calculate_return_drawdown_ratio(
        total_return=0.1,
        max_drawdown=0,
    ) is None

    assert service._calculate_buy_and_hold_return([]) is None
    assert service._calculate_buy_and_hold_return(
        build_uptrend_candles(symbol="BTONE", count=1)
    ) is None


async def test_run_backtest_response_contains_performance_metrics() -> None:
    candles = build_uptrend_candles(symbol="BTRESP", count=40)
    request = _backtest_request(candles)

    service = BacktestService(
        None,
        data_service=FakeBacktestDataService(candles),
    )

    result = await service.run_backtest(request)

    assert result.status == "available"
    assert result.metrics is not None
    assert result.daily_equity

    metrics = result.metrics
    daily_returns = [
        item.daily_return
        for item in result.daily_equity
        if item.daily_return is not None
    ]

    assert metrics.final_equity == result.daily_equity[-1].total_equity
    assert metrics.total_return == pytest.approx(0.031122)
    assert metrics.annualized_return is not None
    assert metrics.average_daily_return == pytest.approx(
        sum(daily_returns) / len(daily_returns)
    )

    assert metrics.daily_return_volatility is not None
    assert metrics.annualized_volatility == pytest.approx(
        metrics.daily_return_volatility * math.sqrt(252)
    )
    assert metrics.sharpe_ratio is not None

    assert metrics.buy_and_hold_return == pytest.approx(0.39)
    assert metrics.excess_return == pytest.approx(
        metrics.total_return - metrics.buy_and_hold_return
    )
    assert metrics.outperformed_buy_and_hold is False