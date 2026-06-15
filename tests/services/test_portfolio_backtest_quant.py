"""组合回测专项测试。

验证多资产共同交易日对齐、初始建仓、目标权重、调仓频率和组合绩效指标。
组合回测同样只反映历史模拟，不代表未来收益。
"""

import math
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.backtest import BacktestRiskControlConfig
from app.schemas.portfolio_backtest import (
    PortfolioBacktestAsset,
    PortfolioBacktestDailyEquity,
    PortfolioBacktestInputSnapshot,
    PortfolioBacktestRequest,
    PortfolioBacktestTrade,
)
from app.services.portfolio_backtest_data_service import (
    PortfolioBacktestCandleData,
    PortfolioBacktestDataService,
)
from app.services.portfolio_backtest_query_service import PortfolioBacktestQueryService
from app.services.portfolio_backtest_service import PortfolioBacktestService
from tests.fixtures.quant_data import (
    build_downtrend_candles,
    build_market_symbol_payload,
    build_missing_date_candles,
    build_uptrend_candles,
    persist_quant_symbol_and_candles,
)


class FakePortfolioBacktestDataService:
    def __init__(self, candles_by_symbol: dict[str, list]) -> None:
        self.candles_by_symbol = candles_by_symbol

    async def get_candles_for_portfolio_backtest(
        self,
        request: PortfolioBacktestRequest,
    ) -> PortfolioBacktestCandleData:
        common_trade_dates = _common_trade_dates(self.candles_by_symbol)

        return PortfolioBacktestCandleData(
            candles_by_symbol=self.candles_by_symbol,
            common_trade_dates=common_trade_dates,
            input_snapshot=PortfolioBacktestInputSnapshot(
                asset_count=len(request.assets),
                candle_count_by_symbol={
                    symbol_key: len(candles)
                    for symbol_key, candles in self.candles_by_symbol.items()
                },
                first_trade_date=common_trade_dates[0],
                last_trade_date=common_trade_dates[-1],
                timeframe=request.timeframe,
                adjust_type=request.adjust_type,
                source=request.source,
                min_required_candles=request.min_required_candles,
                cash_deploy_ratio=request.cash_deploy_ratio,
                rebalance_frequency=request.rebalance_frequency,
                rebalance_interval_days=request.rebalance_interval_days,
                target_weights={
                    f"{asset.market}:{asset.symbol}": asset.target_weight
                    for asset in request.assets
                },
                risk_control=request.risk_control,
            ),
            warnings=[],
        )


def _asset(
    symbol: str,
    weight: str,
) -> PortfolioBacktestAsset:
    return PortfolioBacktestAsset(
        symbol=symbol,
        market="US",
        target_weight=Decimal(weight),
    )


def _symbol_key(symbol: str) -> str:
    return f"US:{symbol}"


def _common_trade_dates(candles_by_symbol: dict[str, list]) -> list:
    date_sets = [
        {candle.candle_time.date() for candle in candles}
        for candles in candles_by_symbol.values()
    ]
    return sorted(set.intersection(*date_sets))


def _portfolio_request(
    candles_by_symbol: dict[str, list],
    *,
    assets: list[PortfolioBacktestAsset] | None = None,
    initial_cash: Decimal = Decimal("100000"),
    cash_deploy_ratio: float = 1.0,
    rebalance_frequency: str = "none",
    rebalance_interval_days: int | None = None,
    risk_control: BacktestRiskControlConfig | None = None,
    include_trades: bool = True,
    include_daily_equity: bool = True,
    include_position_snapshots: bool = True,
    min_required_candles: int = 30,
) -> PortfolioBacktestRequest:
    common_dates = _common_trade_dates(candles_by_symbol)

    return PortfolioBacktestRequest(
        assets=assets
        or [
            _asset("PTAAA", "0.5"),
            _asset("PTBBB", "0.5"),
        ],
        start_date=common_dates[0],
        end_date=common_dates[-1],
        timeframe="1d",
        initial_cash=initial_cash,
        cash_deploy_ratio=cash_deploy_ratio,
        rebalance_frequency=rebalance_frequency,
        rebalance_interval_days=rebalance_interval_days,
        risk_control=risk_control or BacktestRiskControlConfig(),
        adjust_type="none",
        source="mock",
        min_required_candles=min_required_candles,
        enforce_data_quality=False,
        data_quality_stale_after_days=None,
        include_trades=include_trades,
        include_daily_equity=include_daily_equity,
        include_position_snapshots=include_position_snapshots,
    )


def _portfolio_trade(
    *,
    sequence_no: int,
    symbol: str,
    action: str,
    reason: str,
    trade_date,
    trade_value: Decimal,
    commission: Decimal = Decimal("0"),
    slippage_cost: Decimal = Decimal("0"),
) -> PortfolioBacktestTrade:
    return PortfolioBacktestTrade(
        sequence_no=sequence_no,
        symbol=symbol,
        market="US",
        action=action,
        reason=reason,
        trade_date=trade_date,
        price=Decimal("100"),
        quantity=int(trade_value // Decimal("100")) or 1,
        raw_price=Decimal("100"),
        execution_price_type="next_open",
        trade_value=trade_value,
        commission=commission,
        slippage_amount=Decimal("0"),
        slippage_cost=slippage_cost,
        cash_before=Decimal("100000"),
        cash_after=Decimal("100000"),
        position_before=0,
        position_after=1,
        target_weight=Decimal("0.5"),
        actual_weight_before=None,
        actual_weight_after=Decimal("0.5"),
        portfolio_equity_after=Decimal("100000"),
    )


def _daily_equity(
    candles,
    *,
    cash_values: list[Decimal],
    position_values: list[Decimal],
) -> list[PortfolioBacktestDailyEquity]:
    result: list[PortfolioBacktestDailyEquity] = []
    previous_total_equity: Decimal | None = None
    high_watermark = Decimal("0")

    for candle, cash, position_market_value in zip(
        candles,
        cash_values,
        position_values,
        strict=True,
    ):
        total_equity = cash + position_market_value

        if total_equity > high_watermark:
            high_watermark = total_equity

        daily_return = None
        if previous_total_equity is not None and previous_total_equity > 0:
            daily_return = float((total_equity - previous_total_equity) / previous_total_equity)

        drawdown = 0.0
        if high_watermark > 0 and total_equity < high_watermark:
            drawdown = float((high_watermark - total_equity) / high_watermark)

        result.append(
            PortfolioBacktestDailyEquity(
                trade_date=candle.candle_time.date(),
                cash=cash,
                position_market_value=position_market_value,
                total_equity=total_equity,
                daily_return=daily_return,
                drawdown=drawdown,
                positions=[],
            )
        )

        previous_total_equity = total_equity

    return result


def test_portfolio_request_rejects_duplicate_assets_and_invalid_weights() -> None:
    candles_by_symbol = {
        _symbol_key("PTAAA"): build_uptrend_candles(symbol="PTAAA", count=40),
        _symbol_key("PTBBB"): build_downtrend_candles(symbol="PTBBB", count=40),
    }

    with pytest.raises(ValidationError):
        _portfolio_request(
            candles_by_symbol,
            assets=[
                _asset("PTAAA", "0.5"),
                _asset("PTAAA", "0.5"),
            ],
        )

    with pytest.raises(ValidationError):
        _portfolio_request(
            candles_by_symbol,
            assets=[
                _asset("PTAAA", "0.7"),
                _asset("PTBBB", "0.7"),
            ],
        )

    with pytest.raises(ValidationError):
        _portfolio_request(
            candles_by_symbol,
            rebalance_frequency="interval",
            rebalance_interval_days=None,
        )


def test_data_service_builds_common_trade_dates() -> None:
    candles_by_symbol = {
        _symbol_key("PTAAA"): build_uptrend_candles(symbol="PTAAA", count=40),
        _symbol_key("PTBBB"): build_missing_date_candles(
            symbol="PTBBB",
            count=40,
            missing_index=10,
        ),
    }

    common_dates = PortfolioBacktestDataService(None)._build_common_trade_dates(
        candles_by_symbol
    )

    assert len(common_dates) == 39
    assert candles_by_symbol[_symbol_key("PTAAA")][10].candle_time.date() not in common_dates
    assert common_dates == sorted(common_dates)


def test_should_rebalance_respects_frequency_rules() -> None:
    candles_by_symbol = {
        _symbol_key("PTAAA"): build_uptrend_candles(symbol="PTAAA", count=40),
        _symbol_key("PTBBB"): build_downtrend_candles(symbol="PTBBB", count=40),
    }
    common_dates = _common_trade_dates(candles_by_symbol)
    service = PortfolioBacktestService(None)

    none_request = _portfolio_request(candles_by_symbol, rebalance_frequency="none")
    daily_request = _portfolio_request(candles_by_symbol, rebalance_frequency="daily")
    weekly_request = _portfolio_request(candles_by_symbol, rebalance_frequency="weekly")
    monthly_request = _portfolio_request(candles_by_symbol, rebalance_frequency="monthly")
    interval_request = _portfolio_request(
        candles_by_symbol,
        rebalance_frequency="interval",
        rebalance_interval_days=3,
    )

    assert service._should_rebalance(
        request=none_request,
        trade_day_index=0,
        common_trade_dates=common_dates,
    ) is False
    assert service._should_rebalance(
        request=daily_request,
        trade_day_index=0,
        common_trade_dates=common_dates,
    ) is True
    assert service._should_rebalance(
        request=weekly_request,
        trade_day_index=4,
        common_trade_dates=common_dates,
    ) is True
    assert service._should_rebalance(
        request=monthly_request,
        trade_day_index=19,
        common_trade_dates=common_dates,
    ) is True
    assert service._should_rebalance(
        request=interval_request,
        trade_day_index=2,
        common_trade_dates=common_dates,
    ) is True
    assert service._should_rebalance(
        request=daily_request,
        trade_day_index=len(common_dates) - 1,
        common_trade_dates=common_dates,
    ) is False


async def test_run_portfolio_backtest_builds_initial_positions_and_daily_equity() -> None:
    candles_by_symbol = {
        _symbol_key("PTAAA"): build_uptrend_candles(symbol="PTAAA", count=40),
        _symbol_key("PTBBB"): build_downtrend_candles(symbol="PTBBB", count=40),
    }
    request = _portfolio_request(
        candles_by_symbol,
        rebalance_frequency="none",
        include_position_snapshots=True,
    )

    result = await PortfolioBacktestService(
        None,
        data_service=FakePortfolioBacktestDataService(candles_by_symbol),
    ).run_portfolio_backtest(request)

    assert result.status == "available"
    assert result.metrics is not None
    assert result.input_snapshot is not None

    assert len(result.trades) == 2
    assert all(trade.action == "buy" for trade in result.trades)
    assert all(trade.reason == "initial_build" for trade in result.trades)
    assert {trade.symbol for trade in result.trades} == {"PTAAA", "PTBBB"}

    assert len(result.daily_equity) == 40
    first_day = result.daily_equity[0]
    assert first_day.cash >= Decimal("0")
    assert first_day.position_market_value > Decimal("0")
    assert first_day.total_equity == first_day.cash + first_day.position_market_value
    assert len(first_day.positions) == 2

    position_value_sum = sum(
        (position.market_value for position in first_day.positions),
        Decimal("0"),
    )
    assert first_day.position_market_value == position_value_sum

    weight_sum = sum(
        (position.actual_weight for position in first_day.positions),
        Decimal("0"),
    )
    cash_weight = first_day.cash / first_day.total_equity
    assert float(weight_sum + cash_weight) == pytest.approx(1.0)


def test_execute_rebalance_sells_overweight_asset_and_buys_underweight_asset() -> None:
    candles_by_symbol = {
        _symbol_key("PTAAA"): build_uptrend_candles(symbol="PTAAA", count=40),
        _symbol_key("PTBBB"): build_downtrend_candles(symbol="PTBBB", count=40),
    }
    request = _portfolio_request(
        candles_by_symbol,
        rebalance_frequency="daily",
        risk_control=BacktestRiskControlConfig(
            commission_rate=0.001,
            min_commission=Decimal("1"),
            slippage_rate=0.001,
        ),
    )
    service = PortfolioBacktestService(None)
    candle_by_symbol_and_date = service._build_candle_by_symbol_and_date(
        candles_by_symbol
    )
    execution_date = _common_trade_dates(candles_by_symbol)[1]

    positions_by_symbol = {
        _symbol_key("PTAAA"): 700,
        _symbol_key("PTBBB"): 300,
    }
    entry_price_by_symbol = {
        _symbol_key("PTAAA"): Decimal("100"),
        _symbol_key("PTBBB"): Decimal("140"),
    }
    trades: list[PortfolioBacktestTrade] = []

    cash_after = service._execute_rebalance(
        request=request,
        execution_date=execution_date,
        portfolio_equity=Decimal("100000"),
        current_values_by_symbol={
            _symbol_key("PTAAA"): Decimal("70000"),
            _symbol_key("PTBBB"): Decimal("30000"),
        },
        cash=Decimal("10000"),
        positions_by_symbol=positions_by_symbol,
        entry_price_by_symbol=entry_price_by_symbol,
        candle_by_symbol_and_date=candle_by_symbol_and_date,
        trades=trades,
    )

    assert cash_after >= Decimal("0")
    assert len(trades) >= 2
    assert any(
        trade.symbol == "PTAAA"
        and trade.action == "sell"
        and trade.reason == "rebalance"
        for trade in trades
    )
    assert any(
        trade.symbol == "PTBBB"
        and trade.action == "buy"
        and trade.reason == "rebalance"
        for trade in trades
    )

    assert positions_by_symbol[_symbol_key("PTAAA")] < 700
    assert positions_by_symbol[_symbol_key("PTBBB")] > 300
    assert all(trade.commission >= Decimal("1") for trade in trades)
    assert all(trade.execution_price_type == "next_open_with_slippage" for trade in trades)


def test_build_metrics_calculates_portfolio_performance_and_turnover() -> None:
    candles = build_uptrend_candles(symbol="PTMET", count=3)
    candles_by_symbol = {
        _symbol_key("PTAAA"): build_uptrend_candles(symbol="PTAAA", count=40),
        _symbol_key("PTBBB"): build_downtrend_candles(symbol="PTBBB", count=40),
    }
    request = _portfolio_request(candles_by_symbol)

    daily_equity = _daily_equity(
        candles,
        cash_values=[
            Decimal("10000"),
            Decimal("12000"),
            Decimal("11000"),
        ],
        position_values=[
            Decimal("90000"),
            Decimal("90000"),
            Decimal("90000"),
        ],
    )
    trades = [
        _portfolio_trade(
            sequence_no=1,
            symbol="PTAAA",
            action="buy",
            reason="initial_build",
            trade_date=candles[0].candle_time.date(),
            trade_value=Decimal("50000"),
            commission=Decimal("5"),
            slippage_cost=Decimal("10"),
        ),
        _portfolio_trade(
            sequence_no=2,
            symbol="PTAAA",
            action="sell",
            reason="rebalance",
            trade_date=candles[1].candle_time.date(),
            trade_value=Decimal("1000"),
            commission=Decimal("1"),
            slippage_cost=Decimal("2"),
        ),
        _portfolio_trade(
            sequence_no=3,
            symbol="PTBBB",
            action="buy",
            reason="rebalance",
            trade_date=candles[1].candle_time.date(),
            trade_value=Decimal("2000"),
            commission=Decimal("2"),
            slippage_cost=Decimal("3"),
        ),
    ]

    metrics = PortfolioBacktestService(None)._build_metrics(
        request=request,
        daily_equity=daily_equity,
        trades=trades,
    )

    daily_returns = [
        item.daily_return for item in daily_equity if item.daily_return is not None
    ]
    average_daily_return = sum(daily_returns) / len(daily_returns)
    variance = sum(
        (daily_return - average_daily_return) ** 2
        for daily_return in daily_returns
    ) / (len(daily_returns) - 1)
    daily_return_volatility = math.sqrt(variance)

    average_total_equity = (
        sum((item.total_equity for item in daily_equity), Decimal("0"))
        / Decimal(len(daily_equity))
    )
    expected_turnover = float(Decimal("3000") / average_total_equity)

    assert metrics.initial_cash == Decimal("100000")
    assert metrics.final_equity == Decimal("101000")
    assert metrics.total_return == pytest.approx(0.01)
    assert metrics.annualized_return is not None

    assert metrics.average_daily_return == pytest.approx(average_daily_return)
    assert metrics.daily_return_volatility == pytest.approx(daily_return_volatility)
    assert metrics.annualized_volatility == pytest.approx(
        daily_return_volatility * math.sqrt(252)
    )
    assert metrics.sharpe_ratio == pytest.approx(
        average_daily_return / daily_return_volatility * math.sqrt(252)
    )

    assert metrics.trade_count == 3
    assert metrics.buy_count == 2
    assert metrics.sell_count == 1
    assert metrics.rebalance_count == 1

    assert metrics.total_commission == Decimal("8")
    assert metrics.total_slippage_cost == Decimal("15")
    assert metrics.turnover_rate == pytest.approx(expected_turnover)
    assert metrics.best_day_return == pytest.approx(max(daily_returns))
    assert metrics.worst_day_return == pytest.approx(min(daily_returns))

    assert metrics.average_cash_ratio == pytest.approx(
        sum(float(item.cash / item.total_equity) for item in daily_equity)
        / len(daily_equity)
    )
    assert metrics.average_position_ratio == pytest.approx(
        sum(float(item.position_market_value / item.total_equity) for item in daily_equity)
        / len(daily_equity)
    )


async def test_run_portfolio_backtest_can_hide_optional_lists_and_positions() -> None:
    candles_by_symbol = {
        _symbol_key("PTAAA"): build_uptrend_candles(symbol="PTAAA", count=40),
        _symbol_key("PTBBB"): build_downtrend_candles(symbol="PTBBB", count=40),
    }
    request = _portfolio_request(
        candles_by_symbol,
        rebalance_frequency="none",
        include_trades=False,
        include_daily_equity=False,
        include_position_snapshots=False,
    )

    result = await PortfolioBacktestService(
        None,
        data_service=FakePortfolioBacktestDataService(candles_by_symbol),
    ).run_portfolio_backtest(request)

    assert result.status == "available"
    assert result.metrics is not None
    assert result.trades == []
    assert result.daily_equity == []


async def test_portfolio_backtest_query_service_runs_database_candles(db_session) -> None:
    aaa_candles = build_uptrend_candles(symbol="PTDBA", count=40)
    bbb_candles = build_downtrend_candles(symbol="PTDBB", count=40)

    await persist_quant_symbol_and_candles(
        db_session,
        symbol_payload=build_market_symbol_payload(symbol="PTDBA"),
        candle_payloads=aaa_candles,
    )
    await persist_quant_symbol_and_candles(
        db_session,
        symbol_payload=build_market_symbol_payload(symbol="PTDBB"),
        candle_payloads=bbb_candles,
    )

    candles_by_symbol = {
        _symbol_key("PTDBA"): aaa_candles,
        _symbol_key("PTDBB"): bbb_candles,
    }
    request = _portfolio_request(
        candles_by_symbol,
        assets=[
            _asset("PTDBA", "0.5"),
            _asset("PTDBB", "0.5"),
        ],
        rebalance_frequency="none",
        min_required_candles=40,
    )

    result = await PortfolioBacktestQueryService(db_session).run_portfolio_backtest(
        request
    )

    assert result.status == "available"
    assert result.metrics is not None
    assert result.input_snapshot is not None
    assert result.input_snapshot.asset_count == 2
    assert result.input_snapshot.source == "mock"
    assert result.input_snapshot.candle_count_by_symbol["US:PTDBA"] == 40
    assert result.input_snapshot.candle_count_by_symbol["US:PTDBB"] == 40

    assert len(result.trades) == 2
    assert len(result.daily_equity) == 40
    assert result.metrics.trade_count == 2
    assert result.metrics.buy_count == 2
    assert result.metrics.sell_count == 0
