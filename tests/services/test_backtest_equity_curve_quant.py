"""单股回测资金曲线专项测试。

验证按时间顺序推进、模拟买卖、现金、持仓、市值、每日收益和最终权益。
历史回测只验证历史规则表现，不代表未来收益。
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.schemas.backtest import (
    BacktestInputSnapshot,
    BacktestRequest,
    BacktestTrade,
)
from app.services.backtest_data_service import BacktestCandleData
from app.services.backtest_query_service import BacktestQueryService
from app.services.backtest_service import BacktestService
from tests.fixtures.quant_data import (
    build_market_symbol_payload,
    build_uptrend_candles,
    persist_quant_symbol_and_candles,
)


class FakeBacktestDataService:
    def __init__(self, candles) -> None:
        self.candles = candles

    async def get_candles_for_backtest(self, request: BacktestRequest) -> BacktestCandleData:
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
    position_size_ratio: float = 1.0,
    include_trades: bool = True,
    include_daily_equity: bool = True,
    include_signal_snapshots: bool = True,
) -> BacktestRequest:
    return BacktestRequest(
        symbol=candles[0].symbol,
        market="US",
        start_date=candles[0].candle_time.date(),
        end_date=candles[-1].candle_time.date(),
        timeframe="1d",
        initial_cash=initial_cash,
        position_size_ratio=position_size_ratio,
        adjust_type="none",
        source="mock",
        min_required_candles=35,
        enforce_data_quality=False,
        data_quality_stale_after_days=None,
        include_trades=include_trades,
        include_daily_equity=include_daily_equity,
        include_signal_snapshots=include_signal_snapshots,
    )


def _manual_buy_trade(candles) -> BacktestTrade:
    return BacktestTrade(
        sequence_no=1,
        action="buy",
        trade_date=candles[1].candle_time.date(),
        price=Decimal("101"),
        quantity=100,
        raw_price=Decimal("101"),
        slippage_amount=Decimal("0"),
        slippage_rate=0.0,
        commission=Decimal("0"),
        commission_rate=0.0,
        risk_rule=None,
        signal_date=candles[0].candle_time.date(),
        execution_price_type="next_open",
        trade_value=Decimal("10100"),
        cash_before=Decimal("100000"),
        cash_after=Decimal("89900"),
        position_before=0,
        position_after=100,
        equity_after=Decimal("100000"),
        realized_pnl=None,
        realized_return=None,
        holding_days=None,
        signal="buy",
        signal_strength="strong",
        signal_score=90,
        reason="manual buy for equity curve test",
    )


def _manual_sell_trade(candles) -> BacktestTrade:
    return BacktestTrade(
        sequence_no=2,
        action="sell",
        trade_date=candles[3].candle_time.date(),
        price=Decimal("103"),
        quantity=100,
        raw_price=Decimal("103"),
        slippage_amount=Decimal("0"),
        slippage_rate=0.0,
        commission=Decimal("0"),
        commission_rate=0.0,
        risk_rule=None,
        signal_date=candles[2].candle_time.date(),
        execution_price_type="next_open",
        trade_value=Decimal("10300"),
        cash_before=Decimal("89900"),
        cash_after=Decimal("100200"),
        position_before=100,
        position_after=0,
        equity_after=Decimal("100200"),
        realized_pnl=Decimal("200"),
        realized_return=float(Decimal("200") / Decimal("10100")),
        holding_days=2,
        signal="sell",
        signal_strength="strong",
        signal_score=10,
        reason="manual sell for equity curve test",
    )


def test_build_daily_equity_applies_buy_and_sell_trades() -> None:
    candles = build_uptrend_candles(symbol="BTMAN", count=5)
    request = _backtest_request(candles)
    trades = [
        _manual_buy_trade(candles),
        _manual_sell_trade(candles),
    ]

    service = BacktestService(None)
    daily_equity = service._build_daily_equity(
        request=request,
        candles=candles,
        trades=trades,
    )

    assert len(daily_equity) == 5

    assert daily_equity[0].cash == Decimal("100000")
    assert daily_equity[0].position_quantity == 0
    assert daily_equity[0].position_market_value == Decimal("0.0000")
    assert daily_equity[0].total_equity == Decimal("100000.0000")
    assert daily_equity[0].daily_return is None

    assert daily_equity[1].cash == Decimal("89900")
    assert daily_equity[1].position_quantity == 100
    assert daily_equity[1].position_market_value == Decimal("10100.0000")
    assert daily_equity[1].total_equity == Decimal("100000.0000")
    assert daily_equity[1].daily_return == 0.0

    assert daily_equity[2].cash == Decimal("89900")
    assert daily_equity[2].position_quantity == 100
    assert daily_equity[2].position_market_value == Decimal("10200.0000")
    assert daily_equity[2].total_equity == Decimal("100100.0000")
    assert daily_equity[2].daily_return == pytest.approx(0.001)

    assert daily_equity[3].cash == Decimal("100200")
    assert daily_equity[3].position_quantity == 0
    assert daily_equity[3].position_market_value == Decimal("0.0000")
    assert daily_equity[3].total_equity == Decimal("100200.0000")
    assert daily_equity[3].daily_return == pytest.approx(
        float(Decimal("100") / Decimal("100100"))
    )

    assert daily_equity[4].cash == Decimal("100200")
    assert daily_equity[4].position_quantity == 0
    assert daily_equity[4].total_equity == Decimal("100200.0000")
    assert daily_equity[4].daily_return == 0.0


def test_build_metrics_matches_daily_equity_and_trade_accounting() -> None:
    candles = build_uptrend_candles(symbol="BTMET", count=5)
    request = _backtest_request(candles)
    trades = [
        _manual_buy_trade(candles),
        _manual_sell_trade(candles),
    ]

    service = BacktestService(None)
    daily_equity = service._build_daily_equity(
        request=request,
        candles=candles,
        trades=trades,
    )
    metrics = service._build_metrics(
        request=request,
        candles=candles,
        trades=trades,
        daily_equity=daily_equity,
        signal_snapshots=[],
    )

    assert metrics.initial_cash == Decimal("100000")
    assert metrics.final_equity == Decimal("100200.0000")
    assert metrics.total_return == pytest.approx(0.002)

    assert metrics.trade_count == 2
    assert metrics.buy_count == 1
    assert metrics.sell_count == 1

    assert metrics.completed_trade_count == 1
    assert metrics.winning_trade_count == 1
    assert metrics.losing_trade_count == 0
    assert metrics.win_rate == 1.0

    assert metrics.average_win == Decimal("200")
    assert metrics.average_loss is None
    assert metrics.best_trade_pnl == Decimal("200")
    assert metrics.worst_trade_pnl == Decimal("200")

    assert metrics.holding_days == 2
    assert metrics.cash_days == 3

    assert metrics.buy_and_hold_return == pytest.approx(0.04)
    assert metrics.excess_return == pytest.approx(-0.038)
    assert metrics.outperformed_buy_and_hold is False


async def test_run_backtest_uses_next_open_price_and_builds_equity_curve() -> None:
    candles = build_uptrend_candles(symbol="BTUP", count=40)
    request = _backtest_request(candles)

    service = BacktestService(
        None,
        data_service=FakeBacktestDataService(candles),
    )

    result = await service.run_backtest(request)

    assert result.status == "available"
    assert result.metrics is not None
    assert "阶段" not in result.summary
    assert "步骤" not in result.summary
    assert "ReAct" not in result.summary
    assert all("阶段" not in warning for warning in result.warnings)
    assert len(result.trades) == 1
    assert len(result.daily_equity) == 40
    assert len(result.signal_snapshots) == 40

    assert all(snapshot.decision == "skip" for snapshot in result.signal_snapshots[:34])
    assert result.signal_snapshots[34].decision == "buy"

    buy_trade = result.trades[0]
    assert buy_trade.action == "buy"
    assert buy_trade.trade_date == candles[35].candle_time.date()
    assert buy_trade.signal_date == candles[34].candle_time.date()
    assert buy_trade.price == Decimal("134.8000")
    assert buy_trade.quantity == 741
    assert buy_trade.trade_value == Decimal("99886.8000")
    assert buy_trade.cash_before == Decimal("100000")
    assert buy_trade.cash_after == Decimal("113.2000")
    assert buy_trade.position_after == 741

    assert result.daily_equity[34].cash == Decimal("100000")
    assert result.daily_equity[34].position_quantity == 0
    assert result.daily_equity[34].total_equity == Decimal("100000.0000")

    assert result.daily_equity[35].cash == Decimal("113.2000")
    assert result.daily_equity[35].position_quantity == 741
    assert result.daily_equity[35].position_market_value == Decimal("100035.0000")
    assert result.daily_equity[35].total_equity == Decimal("100148.2000")

    assert result.daily_equity[-1].total_equity == Decimal("103112.2000")
    assert result.metrics.final_equity == Decimal("103112.2000")
    assert result.metrics.total_return == pytest.approx(0.031122)
    assert result.metrics.trade_count == 1
    assert result.metrics.buy_count == 1
    assert result.metrics.sell_count == 0
    assert result.metrics.holding_days == 5
    assert result.metrics.cash_days == 35


async def test_run_backtest_can_hide_optional_lists() -> None:
    candles = build_uptrend_candles(symbol="BTHIDE", count=40)
    request = _backtest_request(
        candles,
        include_trades=False,
        include_daily_equity=False,
        include_signal_snapshots=False,
    )

    service = BacktestService(
        None,
        data_service=FakeBacktestDataService(candles),
    )

    result = await service.run_backtest(request)

    assert result.status == "available"
    assert result.metrics is not None
    assert result.trades == []
    assert result.daily_equity == []
    assert result.signal_snapshots == []
    assert result.metrics.final_equity == Decimal("103112.2000")


async def test_backtest_query_service_runs_database_candles(db_session) -> None:
    candle_payloads = build_uptrend_candles(symbol="BTDB", count=40)

    await persist_quant_symbol_and_candles(
        db_session,
        symbol_payload=build_market_symbol_payload(symbol="BTDB"),
        candle_payloads=candle_payloads,
    )

    request = _backtest_request(candle_payloads)
    request.enforce_data_quality = True
    request.data_quality_stale_after_days = 3650

    result = await BacktestQueryService(db_session).run_backtest(request)

    assert result.status == "available"
    assert result.metrics is not None
    assert result.input_snapshot is not None
    assert result.input_snapshot.candle_count == 40
    assert result.input_snapshot.source == "mock"

    assert len(result.trades) == 1
    assert len(result.daily_equity) == 40

    assert result.metrics.final_equity == Decimal("103112.2000")
    assert result.metrics.total_return == pytest.approx(0.031122)
