from datetime import UTC, datetime, date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_candle import MarketCandle
from app.schemas.backtest import (
    BacktestDailyEquity,
    BacktestMetrics,
    BacktestRequest,
    BacktestResponse,
    BacktestSignalSnapshot,
    BacktestTrade,
)
from app.schemas.technical_indicator import (
    TechnicalIndicatorResponse,
    TechnicalIndicatorSummary,
)
from app.services.backtest_data_service import BacktestDataService
from app.services.indicator_dataframe_service import IndicatorDataFrameService
from app.services.strategy_signal_service import StrategySignalService
from app.services.technical_indicator_service import TechnicalIndicatorService


class BacktestService:
    """Run the first version of strategy-signal backtests.

    Step 5 focuses on the backtest loop and daily signal generation.
    Trade execution, position accounting, and detailed metrics are added
    in later stage-six steps.
    """

    MIN_SIGNAL_WINDOW = 35

    def __init__(
        self,
        db: AsyncSession,
        *,
        data_service: BacktestDataService | None = None,
        dataframe_service: IndicatorDataFrameService | None = None,
        indicator_service: TechnicalIndicatorService | None = None,
        strategy_signal_service: StrategySignalService | None = None,
    ) -> None:
        self.db = db
        self.data_service = data_service or BacktestDataService(db)
        self.dataframe_service = dataframe_service or IndicatorDataFrameService()
        self.indicator_service = indicator_service or TechnicalIndicatorService()
        self.strategy_signal_service = (
            strategy_signal_service or StrategySignalService()
        )

    async def run_backtest(
        self,
        request: BacktestRequest,
    ) -> BacktestResponse:
        candle_data = await self.data_service.get_candles_for_backtest(request)
        candles = candle_data.candles

        signal_snapshots = self._build_signal_snapshots(
            request=request,
            candles=candles,
        )
        trades = self._match_trades(
            request=request,
            candles=candles,
            signal_snapshots=signal_snapshots,
        )
        daily_equity = self._build_daily_equity(
            request=request,
            candles=candles,
            trades=trades,
        )
        metrics = self._build_metrics(
            request=request,
            trades=trades,
            daily_equity=daily_equity,
        )

        return BacktestResponse(
            symbol=request.symbol,
            market=request.market,
            start_date=request.start_date,
            end_date=request.end_date,
            status="available",
            unavailable_reason=None,
            summary=self._build_summary(
                request=request,
                candle_count=len(candles),
                signal_count=len(signal_snapshots),
                metrics=metrics,
            ),
            metrics=metrics,
            trades=trades if request.include_trades else [],
            daily_equity=daily_equity if request.include_daily_equity else [],
            signal_snapshots=(
                signal_snapshots if request.include_signal_snapshots else []
            ),
            input_snapshot=candle_data.input_snapshot,
            warnings=[
                *candle_data.warnings,
                "当前为阶段六步骤九：已完成交易明细增强，包含信号日期、成交金额、已实现盈亏、已实现收益率和持仓天数；本阶段暂未计算手续费和滑点。",
            ],
        )

    def _build_signal_snapshots(
        self,
        *,
        request: BacktestRequest,
        candles: list[MarketCandle],
    ) -> list[BacktestSignalSnapshot]:
        snapshots: list[BacktestSignalSnapshot] = []

        for index in range(len(candles)):
            window = candles[: index + 1]
            current_candle = candles[index]

            if len(window) < self.MIN_SIGNAL_WINDOW:
                snapshots.append(
                    BacktestSignalSnapshot(
                        trade_date=current_candle.candle_time.date(),
                        decision="skip",
                        signal=None,
                        signal_strength=None,
                        signal_score=None,
                        close_price=current_candle.close_price,
                        reason=(
                            f"当前历史窗口只有 {len(window)} 根 K 线，"
                            f"少于生成策略信号所需的 {self.MIN_SIGNAL_WINDOW} 根，跳过。"
                        ),
                        warnings=["K 线数量不足，暂不生成策略信号。"],
                    )
                )
                continue

            technical_indicators = self._build_technical_indicators(
                candles=window,
            )
            strategy_signal = self.strategy_signal_service.generate_signal(
                technical_indicators=technical_indicators,
                data_quality=None,
                include_detail=False,
            )

            snapshots.append(
                BacktestSignalSnapshot(
                    trade_date=current_candle.candle_time.date(),
                    decision=self._decision_from_signal(strategy_signal.signal),
                    signal=strategy_signal.signal,
                    signal_strength=strategy_signal.strength,
                    signal_score=strategy_signal.score,
                    close_price=current_candle.close_price,
                    reason=strategy_signal.summary,
                    warnings=strategy_signal.risks,
                )
            )

        return snapshots

    def _build_technical_indicators(
        self,
        *,
        candles: list[MarketCandle],
    ) -> TechnicalIndicatorResponse:
        df = self.dataframe_service.candles_to_dataframe(candles)

        moving_average = self.indicator_service.calculate_moving_average(df)
        rsi = self.indicator_service.calculate_rsi(df)
        macd = self.indicator_service.calculate_macd(df)
        volatility = self.indicator_service.calculate_volatility(df)
        momentum = self.indicator_service.calculate_momentum(df)
        volume_factor = self.indicator_service.calculate_volume_factor(df)

        latest_candle = candles[-1]

        summary = TechnicalIndicatorSummary(
            moving_average=moving_average,
            rsi=rsi,
            macd=macd,
            volatility=volatility,
            momentum=momentum,
            volume_factor=volume_factor,
            interpretation=[
                f"均线趋势为 {moving_average.trend}。",
                f"RSI 状态为 {rsi.status}。",
                f"MACD 信号为 {macd.signal}。",
                f"波动率等级为 {volatility.level}。",
                f"动量方向为 {momentum.direction}。",
                f"成交量状态为 {volume_factor.status}。",
            ],
            warnings=[
                "回测中的技术指标仅使用当前日期及以前的历史 K 线计算。",
                "本回测结果仅用于策略研究，不构成投资建议。",
            ],
        )

        return TechnicalIndicatorResponse(
            symbol=latest_candle.symbol,
            market=latest_candle.market,
            timeframe=latest_candle.timeframe,
            adjust_type=latest_candle.adjust_type,
            source=latest_candle.source,
            candle_count=len(candles),
            calculated_at=datetime.now(UTC),
            summary=summary,
        )

    def _match_trades(
        self,
        *,
        request: BacktestRequest,
        candles: list[MarketCandle],
        signal_snapshots: list[BacktestSignalSnapshot],
    ) -> list[BacktestTrade]:
        trades: list[BacktestTrade] = []
        cash = request.initial_cash
        position_quantity = 0
        open_buy_trade: BacktestTrade | None = None

        for index, snapshot in enumerate(signal_snapshots):
            next_index = index + 1
            if next_index >= len(candles):
                continue

            next_candle = candles[next_index]
            execution_price = next_candle.open_price

            if execution_price <= 0:
                continue

            if snapshot.decision == "buy":
                if position_quantity > 0:
                    continue

                quantity = self._calculate_buy_quantity(
                    cash=cash,
                    price=execution_price,
                    position_size_ratio=request.position_size_ratio,
                )
                if quantity <= 0:
                    continue

                cash_before = cash
                position_before = position_quantity
                cost = execution_price * Decimal(quantity)

                cash = cash - cost
                position_quantity = position_quantity + quantity
                equity_after = cash + Decimal(position_quantity) * execution_price

                trade_value = cost
                trade = BacktestTrade(
                        sequence_no=len(trades) + 1,
                        action="buy",
                        trade_date=next_candle.candle_time.date(),
                        price=execution_price,
                        quantity=quantity,
                        cash_before=cash_before,
                        cash_after=cash,
                        position_before=position_before,
                        position_after=position_quantity,
                        equity_after=equity_after,
                        signal=snapshot.signal,
                        signal_strength=snapshot.signal_strength,
                        signal_score=snapshot.signal_score,
                        reason=self._build_trade_reason(
                            snapshot=snapshot,
                            execution_date=next_candle.candle_time.date(),
                        ),
                        signal_date=snapshot.trade_date,
                        execution_price_type="next_open",
                        trade_value=trade_value,
                        realized_pnl=None,
                        realized_return=None,
                        holding_days=None,
                    )
                trades.append(trade)
                open_buy_trade = trade
                continue

            if snapshot.decision == "sell":
                if position_quantity <= 0:
                    continue

                cash_before = cash
                position_before = position_quantity
                quantity = position_quantity
                proceeds = execution_price * Decimal(quantity)

                trade_value = proceeds
                realized_pnl = None
                realized_return = None
                holding_days = None

                if open_buy_trade is not None:
                    buy_cost = open_buy_trade.price * Decimal(open_buy_trade.quantity)
                    realized_pnl = proceeds - buy_cost

                    if buy_cost > 0:
                        realized_return = float(realized_pnl / buy_cost)

                    holding_days = (
                            next_candle.candle_time.date() - open_buy_trade.trade_date
                    ).days

                cash = cash + proceeds
                position_quantity = 0
                equity_after = cash

                trades.append(
                    BacktestTrade(
                        sequence_no=len(trades) + 1,
                        action="sell",
                        trade_date=next_candle.candle_time.date(),
                        price=execution_price,
                        quantity=quantity,
                        cash_before=cash_before,
                        cash_after=cash,
                        position_before=position_before,
                        position_after=position_quantity,
                        equity_after=equity_after,
                        signal=snapshot.signal,
                        signal_strength=snapshot.signal_strength,
                        signal_score=snapshot.signal_score,
                        reason=self._build_trade_reason(
                            snapshot=snapshot,
                            execution_date=next_candle.candle_time.date(),
                        ),
                        signal_date=snapshot.trade_date,
                        execution_price_type="next_open",
                        trade_value=trade_value,
                        realized_pnl=realized_pnl,
                        realized_return=realized_return,
                        holding_days=holding_days,
                    )
                )
                open_buy_trade = None

        return trades

    def _build_daily_equity(
        self,
        *,
        request: BacktestRequest,
        candles: list[MarketCandle],
        trades: list[BacktestTrade],
    ) -> list[BacktestDailyEquity]:
        result: list[BacktestDailyEquity] = []
        trades_by_date = self._group_trades_by_date(trades)

        cash = request.initial_cash
        position_quantity = 0
        previous_equity: Decimal | None = None
        peak_equity = request.initial_cash

        for candle in candles:
            trade_date = candle.candle_time.date()

            for trade in trades_by_date.get(trade_date, []):
                cash = trade.cash_after
                position_quantity = trade.position_after

            position_market_value = Decimal(position_quantity) * candle.close_price
            total_equity = cash + position_market_value

            if previous_equity is None or previous_equity == 0:
                daily_return = None
            else:
                daily_return = float(
                    (total_equity - previous_equity) / previous_equity
                )

            if total_equity > peak_equity:
                peak_equity = total_equity

            drawdown = 0.0
            if peak_equity > 0:
                drawdown = float((peak_equity - total_equity) / peak_equity)

            result.append(
                BacktestDailyEquity(
                    trade_date=trade_date,
                    close_price=candle.close_price,
                    cash=cash,
                    position_quantity=position_quantity,
                    position_market_value=position_market_value,
                    total_equity=total_equity,
                    daily_return=daily_return,
                    drawdown=drawdown,
                )
            )

            previous_equity = total_equity

        return result

    def _group_trades_by_date(
        self,
        trades: list[BacktestTrade],
    ) -> dict[date, list[BacktestTrade]]:
        grouped: dict[date, list[BacktestTrade]] = {}

        for trade in trades:
            grouped.setdefault(trade.trade_date, []).append(trade)

        return grouped

    def _build_metrics(
        self,
        *,
        request: BacktestRequest,
        trades: list[BacktestTrade],
        daily_equity: list[BacktestDailyEquity],
    ) -> BacktestMetrics:
        final_equity = (
            daily_equity[-1].total_equity
            if daily_equity
            else request.initial_cash
        )

        total_return = float(
            (final_equity - request.initial_cash) / request.initial_cash
        )

        max_drawdown = max(
            (item.drawdown for item in daily_equity),
            default=0.0,
        )

        trade_count = len(trades)
        buy_count = sum(1 for trade in trades if trade.action == "buy")
        sell_count = sum(1 for trade in trades if trade.action == "sell")

        completed_results = self._build_completed_trade_results(trades)
        completed_trade_count = len(completed_results)
        winning_trade_count = sum(1 for result in completed_results if result > 0)
        losing_trade_count = sum(1 for result in completed_results if result < 0)

        if completed_trade_count == 0:
            win_rate = None
        else:
            win_rate = winning_trade_count / completed_trade_count

        holding_days = sum(
            1 for item in daily_equity if item.position_quantity > 0
        )
        cash_days = len(daily_equity) - holding_days

        return BacktestMetrics(
            initial_cash=request.initial_cash,
            final_equity=final_equity,
            total_return=total_return,
            max_drawdown=max_drawdown,
            trade_count=trade_count,
            buy_count=buy_count,
            sell_count=sell_count,
            completed_trade_count=completed_trade_count,
            winning_trade_count=winning_trade_count,
            losing_trade_count=losing_trade_count,
            win_rate=win_rate,
            holding_days=holding_days,
            cash_days=cash_days,
        )

    def _build_completed_trade_results(
        self,
        trades: list[BacktestTrade],
    ) -> list[Decimal]:
        results: list[Decimal] = []

        for trade in trades:
            if trade.action == "sell" and trade.realized_pnl is not None:
                results.append(trade.realized_pnl)

        return results

    def _decision_from_signal(
        self,
        signal,
    ) -> str:
        if signal == "buy":
            return "buy"

        if signal == "sell":
            return "sell"

        if signal == "hold":
            return "hold"

        if signal == "observe":
            return "observe"

        return "skip"

    def _build_summary(
        self,
        *,
        request: BacktestRequest,
        candle_count: int,
        signal_count: int,
        metrics: BacktestMetrics,
    ) -> str:
        return (
            f"{request.market}:{request.symbol} 已完成阶段六回测运行，"
            f"本次读取 {candle_count} 根 K 线，生成 {signal_count} 条每日信号快照，"
            f"共模拟成交 {metrics.trade_count} 次。"
            f"期末权益为 {metrics.final_equity}，"
            f"总收益率为 {metrics.total_return:.2%}，"
            f"最大回撤为 {metrics.max_drawdown:.2%}。"
            "本回测仅用于策略研究，不构成投资建议。"
        )

    def _calculate_buy_quantity(
        self,
        *,
        cash: Decimal,
        price: Decimal,
        position_size_ratio: float,
    ) -> int:
        available_cash = cash * Decimal(str(position_size_ratio))
        return int(available_cash // price)

    def _build_trade_reason(
        self,
        *,
        snapshot: BacktestSignalSnapshot,
        execution_date,
    ) -> str:
        return (
            f"{snapshot.trade_date} 生成 {snapshot.decision} 信号，"
            f"于 {execution_date} 按下一根 K 线开盘价模拟成交；"
            "本回测未计算手续费和滑点。"
        )

