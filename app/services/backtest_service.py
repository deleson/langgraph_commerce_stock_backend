from datetime import UTC, datetime, date
from decimal import Decimal
import math

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_candle import MarketCandle
from app.schemas.backtest import (
    BacktestDailyEquity,
    BacktestExecutionPriceType,
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
            candles=candles,
            trades=trades,
            daily_equity=daily_equity,
            signal_snapshots=signal_snapshots,
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
                "当前为阶段六点二：已支持手续费、滑点、止损、止盈、冷却期和最大回撤保护计算；summary、warnings 和 ReAct 输出将在后续步骤继续优化。",
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
        cooldown_days_left = 0
        peak_equity = request.initial_cash

        for index, snapshot in enumerate(signal_snapshots):
            next_index = index + 1
            if next_index >= len(candles):
                continue

            current_candle = candles[index]
            next_candle = candles[next_index]
            raw_price = next_candle.open_price

            if raw_price <= 0:
                continue

            current_equity = cash + Decimal(position_quantity) * current_candle.close_price

            if current_equity > peak_equity:
                peak_equity = current_equity

            current_drawdown = self._calculate_current_drawdown(
                current_equity=current_equity,
                peak_equity=peak_equity,
            )

            snapshot = self._apply_stop_loss_decision(
                request=request,
                snapshot=snapshot,
                position_quantity=position_quantity,
                open_buy_trade=open_buy_trade,
            )
            signal_snapshots[index] = snapshot

            snapshot = self._apply_take_profit_decision(
                request=request,
                snapshot=snapshot,
                position_quantity=position_quantity,
                open_buy_trade=open_buy_trade,
            )
            signal_snapshots[index] = snapshot

            snapshot = self._apply_drawdown_guard_decision(
                request=request,
                snapshot=snapshot,
                position_quantity=position_quantity,
                current_drawdown=current_drawdown,
            )
            signal_snapshots[index] = snapshot

            cooldown_checked = cooldown_days_left > 0

            snapshot = self._apply_cooldown_decision(
                request=request,
                snapshot=snapshot,
                position_quantity=position_quantity,
                cooldown_days_left=cooldown_days_left,
            )
            signal_snapshots[index] = snapshot

            if snapshot.decision == "buy":
                if position_quantity > 0:
                    continue

                execution_price, slippage_amount, execution_price_type = (
                    self._apply_slippage(
                        raw_price=raw_price,
                        action="buy",
                        slippage_rate=request.risk_control.slippage_rate,
                    )
                )

                quantity = self._calculate_buy_quantity(
                    cash=cash,
                    price=execution_price,
                    position_size_ratio=request.position_size_ratio,
                )
                if quantity <= 0:
                    continue

                cash_before = cash
                position_before = position_quantity
                trade_value = execution_price * Decimal(quantity)
                commission = self._calculate_commission(
                    trade_value=trade_value,
                    commission_rate=request.risk_control.commission_rate,
                    min_commission=request.risk_control.min_commission,
                )

                total_cost = trade_value + commission

                if cash < total_cost:
                    quantity = self._calculate_buy_quantity(
                        cash=cash - commission,
                        price=execution_price,
                        position_size_ratio=request.position_size_ratio,
                    )
                    if quantity <= 0:
                        continue

                    trade_value = execution_price * Decimal(quantity)
                    commission = self._calculate_commission(
                        trade_value=trade_value,
                        commission_rate=request.risk_control.commission_rate,
                        min_commission=request.risk_control.min_commission,
                    )
                    total_cost = trade_value + commission

                    if cash < total_cost:
                        continue

                cash = cash - total_cost
                position_quantity = position_quantity + quantity
                equity_after = cash + Decimal(position_quantity) * execution_price
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
                        trade_value=trade_value,
                        realized_pnl=None,
                        realized_return=None,
                        holding_days=None,
                        commission=commission,
                        commission_rate=request.risk_control.commission_rate,
                        risk_rule=None,
                        execution_price_type=execution_price_type,
                        raw_price=raw_price,
                        slippage_amount=slippage_amount,
                        slippage_rate=request.risk_control.slippage_rate,
                    )
                trades.append(trade)
                open_buy_trade = trade
                continue

            if snapshot.decision in {"sell", "stop_loss", "take_profit"}:
                if position_quantity <= 0:
                    continue

                execution_price, slippage_amount, execution_price_type = (
                    self._apply_slippage(
                        raw_price=raw_price,
                        action="sell",
                        slippage_rate=request.risk_control.slippage_rate,
                    )
                )

                cash_before = cash
                position_before = position_quantity
                quantity = position_quantity
                trade_value = execution_price * Decimal(quantity)
                commission = self._calculate_commission(
                    trade_value=trade_value,
                    commission_rate=request.risk_control.commission_rate,
                    min_commission=request.risk_control.min_commission,
                )

                net_proceeds = trade_value - commission
                holding_days = None

                if open_buy_trade is not None:
                    buy_cost = open_buy_trade.trade_value + open_buy_trade.commission
                    realized_pnl = net_proceeds - buy_cost

                    if buy_cost > 0:
                        realized_return = float(realized_pnl / buy_cost)

                    holding_days = (
                            next_candle.candle_time.date() - open_buy_trade.trade_date
                    ).days

                cash = cash + net_proceeds
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
                        execution_price_type=execution_price_type,
                        trade_value=trade_value,
                        realized_pnl=realized_pnl,
                        realized_return=realized_return,
                        holding_days=holding_days,

                        raw_price=raw_price,
                        slippage_amount=slippage_amount,
                        slippage_rate=request.risk_control.slippage_rate,

                        commission=commission,
                        commission_rate=request.risk_control.commission_rate,
                        risk_rule=snapshot.risk_rule,
                    )
                )
                open_buy_trade = None

                if (
                    request.risk_control.enable_cooldown
                    and request.risk_control.cooldown_days > 0
                ):
                    cooldown_days_left = request.risk_control.cooldown_days
            if cooldown_checked and cooldown_days_left > 0:
                cooldown_days_left -= 1

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
        candles: list[MarketCandle],
        trades: list[BacktestTrade],
        daily_equity: list[BacktestDailyEquity],
        signal_snapshots: list[BacktestSignalSnapshot],
    ) -> BacktestMetrics:
        final_equity = (
            daily_equity[-1].total_equity
            if daily_equity
            else request.initial_cash
        )

        total_return = float(
            (final_equity - request.initial_cash) / request.initial_cash
        )

        buy_and_hold_return = self._calculate_buy_and_hold_return(candles)
        excess_return = self._calculate_excess_return(
            total_return=total_return,
            buy_and_hold_return=buy_and_hold_return,
        )
        outperformed_buy_and_hold = self._calculate_outperformed_buy_and_hold(
            excess_return
        )
        total_commission = sum(
            (trade.commission for trade in trades),
            Decimal("0"),
        )
        total_slippage_cost = sum(
            (trade.slippage_amount * Decimal(trade.quantity) for trade in trades),
            Decimal("0"),
        )
        stop_loss_trigger_count = sum(
            1 for trade in trades if trade.risk_rule == "stop_loss"
        )
        take_profit_trigger_count = sum(
            1 for trade in trades if trade.risk_rule == "take_profit"
        )
        cooldown_skip_count = sum(
            1 for snapshot in signal_snapshots if snapshot.decision == "cooldown"
        )
        drawdown_guard_trigger_count = sum(
            1 for snapshot in signal_snapshots if snapshot.decision == "drawdown_guard"
        )


        daily_returns = self._build_daily_returns(daily_equity)
        average_daily_return = self._calculate_average_daily_return(daily_returns)
        annualized_return = self._calculate_annualized_return(
            initial_cash=request.initial_cash,
            final_equity=final_equity,
            trading_days=len(daily_equity),
        )

        daily_return_volatility = self._calculate_daily_return_volatility(
            daily_returns
        )
        annualized_volatility = self._calculate_annualized_volatility(
            daily_return_volatility
        )
        sharpe_ratio = self._calculate_sharpe_ratio(
            average_daily_return=average_daily_return,
            daily_return_volatility=daily_return_volatility,
        )

        max_drawdown = max(
            (item.drawdown for item in daily_equity),
            default=0.0,
        )

        return_drawdown_ratio = self._calculate_return_drawdown_ratio(
            total_return=total_return,
            max_drawdown=max_drawdown,
        )

        trade_count = len(trades)
        buy_count = sum(1 for trade in trades if trade.action == "buy")
        sell_count = sum(1 for trade in trades if trade.action == "sell")

        completed_results = self._build_completed_trade_results(trades)
        completed_trade_count = len(completed_results)
        winning_trade_count = sum(1 for result in completed_results if result > 0)
        losing_trade_count = sum(1 for result in completed_results if result < 0)

        average_win = self._calculate_average_win(completed_results)
        average_loss = self._calculate_average_loss(completed_results)
        profit_loss_ratio = self._calculate_profit_loss_ratio(
            average_win=average_win,
            average_loss=average_loss,
        )
        realized_returns = self._build_realized_returns(trades)
        average_realized_return = self._calculate_average_realized_return(
            realized_returns
        )
        completed_holding_days = self._build_completed_holding_days(trades)
        average_completed_holding_days = self._calculate_average_holding_days(
            completed_holding_days
        )
        best_trade_pnl = self._calculate_best_trade_pnl(completed_results)
        worst_trade_pnl = self._calculate_worst_trade_pnl(completed_results)

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
            daily_return_volatility=daily_return_volatility,
            annualized_volatility=annualized_volatility,
            sharpe_ratio=sharpe_ratio,
            return_drawdown_ratio=return_drawdown_ratio,
            trade_count=trade_count,
            buy_count=buy_count,
            sell_count=sell_count,
            completed_trade_count=completed_trade_count,
            winning_trade_count=winning_trade_count,
            losing_trade_count=losing_trade_count,
            win_rate=win_rate,
            average_win=average_win,
            average_loss=average_loss,
            profit_loss_ratio=profit_loss_ratio,
            average_realized_return=average_realized_return,
            best_trade_pnl=best_trade_pnl,
            worst_trade_pnl=worst_trade_pnl,
            holding_days=holding_days,
            cash_days=cash_days,
            average_holding_days=average_completed_holding_days,
            annualized_return=annualized_return,
            average_daily_return=average_daily_return,
            buy_and_hold_return=buy_and_hold_return,
            excess_return=excess_return,
            outperformed_buy_and_hold=outperformed_buy_and_hold,
            total_commission=total_commission,
            total_slippage_cost=total_slippage_cost,
            stop_loss_trigger_count=stop_loss_trigger_count,
            take_profit_trigger_count=take_profit_trigger_count,
            cooldown_skip_count=cooldown_skip_count,
            drawdown_guard_trigger_count=drawdown_guard_trigger_count,
        )

    def _build_daily_returns(
        self,
        daily_equity: list[BacktestDailyEquity],
    ) -> list[float]:
        return [
            item.daily_return
            for item in daily_equity
            if item.daily_return is not None
        ]

    def _calculate_average_daily_return(
        self,
        daily_returns: list[float],
    ) -> float | None:
        if not daily_returns:
            return None

        return sum(daily_returns) / len(daily_returns)

    def _calculate_annualized_return(
        self,
        *,
        initial_cash: Decimal,
        final_equity: Decimal,
        trading_days: int,
    ) -> float | None:
        if trading_days <= 0:
            return None

        if initial_cash <= 0:
            return None

        equity_ratio = float(final_equity / initial_cash)

        return equity_ratio ** (252 / trading_days) - 1

    def _calculate_daily_return_volatility(
        self,
        daily_returns: list[float],
    ) -> float | None:
        if len(daily_returns) < 2:
            return None

        average_return = sum(daily_returns) / len(daily_returns)
        variance = sum(
            (daily_return - average_return) ** 2
            for daily_return in daily_returns
        ) / (len(daily_returns) - 1)

        return math.sqrt(variance)

    def _calculate_annualized_volatility(
        self,
        daily_return_volatility: float | None,
    ) -> float | None:
        if daily_return_volatility is None:
            return None

        return daily_return_volatility * math.sqrt(252)

    def _calculate_sharpe_ratio(
        self,
        *,
        average_daily_return: float | None,
        daily_return_volatility: float | None,
    ) -> float | None:
        if average_daily_return is None:
            return None

        if daily_return_volatility is None or daily_return_volatility == 0:
            return None

        return average_daily_return / daily_return_volatility * math.sqrt(252)

    def _calculate_return_drawdown_ratio(
        self,
        *,
        total_return: float,
        max_drawdown: float,
    ) -> float | None:
        if max_drawdown <= 0:
            return None

        return total_return / max_drawdown

    def _calculate_current_drawdown(
        self,
        *,
        current_equity: Decimal,
        peak_equity: Decimal,
    ) -> float:
        if peak_equity <= 0:
            return 0.0

        if current_equity >= peak_equity:
            return 0.0

        return float((peak_equity - current_equity) / peak_equity)

    def _calculate_buy_and_hold_return(
        self,
        candles: list[MarketCandle],
    ) -> float | None:
        if len(candles) < 2:
            return None

        first_close = candles[0].close_price
        last_close = candles[-1].close_price

        if first_close <= 0:
            return None

        return float((last_close - first_close) / first_close)

    def _calculate_excess_return(
        self,
        *,
        total_return: float,
        buy_and_hold_return: float | None,
    ) -> float | None:
        if buy_and_hold_return is None:
            return None

        return total_return - buy_and_hold_return

    def _calculate_outperformed_buy_and_hold(
        self,
        excess_return: float | None,
    ) -> bool | None:
        if excess_return is None:
            return None

        return excess_return > 0

    def _build_completed_trade_results(
        self,
        trades: list[BacktestTrade],
    ) -> list[Decimal]:
        results: list[Decimal] = []

        for trade in trades:
            if trade.action == "sell" and trade.realized_pnl is not None:
                results.append(trade.realized_pnl)

        return results

    def _calculate_average_win(
        self,
        completed_results: list[Decimal],
    ) -> Decimal | None:
        wins = [result for result in completed_results if result > 0]
        if not wins:
            return None

        return sum(wins, Decimal("0")) / Decimal(len(wins))

    def _calculate_average_loss(
        self,
        completed_results: list[Decimal],
    ) -> Decimal | None:
        losses = [result for result in completed_results if result < 0]
        if not losses:
            return None

        return sum(losses, Decimal("0")) / Decimal(len(losses))

    def _calculate_profit_loss_ratio(
        self,
        *,
        average_win: Decimal | None,
        average_loss: Decimal | None,
    ) -> float | None:
        if average_win is None or average_loss is None:
            return None

        if average_loss == 0:
            return None

        return float(average_win / abs(average_loss))

    def _build_realized_returns(
        self,
        trades: list[BacktestTrade],
    ) -> list[float]:
        return [
            trade.realized_return
            for trade in trades
            if trade.action == "sell" and trade.realized_return is not None
        ]

    def _calculate_average_realized_return(
        self,
        realized_returns: list[float],
    ) -> float | None:
        if not realized_returns:
            return None

        return sum(realized_returns) / len(realized_returns)

    def _build_completed_holding_days(
        self,
        trades: list[BacktestTrade],
    ) -> list[int]:
        return [
            trade.holding_days
            for trade in trades
            if trade.action == "sell" and trade.holding_days is not None
        ]

    def _calculate_average_holding_days(
        self,
        completed_holding_days: list[int],
    ) -> float | None:
        if not completed_holding_days:
            return None

        return sum(completed_holding_days) / len(completed_holding_days)

    def _calculate_best_trade_pnl(
        self,
        completed_results: list[Decimal],
    ) -> Decimal | None:
        if not completed_results:
            return None

        return max(completed_results)

    def _calculate_worst_trade_pnl(
        self,
        completed_results: list[Decimal],
    ) -> Decimal | None:
        if not completed_results:
            return None

        return min(completed_results)

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

    def _format_percent(
        self,
        value: float | None,
    ) -> str:
        if value is None:
            return "不可计算"

        return f"{value:.2%}"

    def _format_decimal(
        self,
        value: Decimal | None,
    ) -> str:
        if value is None:
            return "不可计算"

        return str(value)

    def _format_float(
        self,
        value: float | None,
    ) -> str:
        if value is None:
            return "不可计算"

        return f"{value:.2f}"

    def _format_bool_result(
        self,
        value: bool | None,
        *,
        true_text: str,
        false_text: str,
    ) -> str:
        if value is None:
            return "不可判断"

        return true_text if value else false_text

    def _build_summary(
        self,
        *,
        request: BacktestRequest,
        candle_count: int,
        signal_count: int,
        metrics: BacktestMetrics,
    ) -> str:
        benchmark_result = self._format_bool_result(
            metrics.outperformed_buy_and_hold,
            true_text="跑赢同股买入持有基准",
            false_text="未跑赢同股买入持有基准",
        )

        return (
            f"{request.market}:{request.symbol} 已完成阶段六点一回测绩效分析，"
            f"本次读取 {candle_count} 根 K 线，生成 {signal_count} 条每日信号快照，"
            f"共模拟成交 {metrics.trade_count} 次。"
            f"期末权益为 {self._format_decimal(metrics.final_equity)}，"
            f"总收益率为 {self._format_percent(metrics.total_return)}，"
            f"年化收益率为 {self._format_percent(metrics.annualized_return)}，"
            f"最大回撤为 {self._format_percent(metrics.max_drawdown)}，"
            f"夏普比率为 {self._format_float(metrics.sharpe_ratio)}，"
            f"胜率为 {self._format_percent(metrics.win_rate)}，"
            f"盈亏比为 {self._format_float(metrics.profit_loss_ratio)}，"
            f"买入持有收益率为 {self._format_percent(metrics.buy_and_hold_return)}，"
            f"超额收益为 {self._format_percent(metrics.excess_return)}，"
            f"{benchmark_result}。"
            "本回测仅基于历史行情和策略规则进行模拟，不构成投资建议，也不代表未来收益。"
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

    def _calculate_commission(
        self,
        *,
        trade_value: Decimal,
        commission_rate: float,
        min_commission: Decimal,
    ) -> Decimal:
        if trade_value <= 0 or commission_rate <= 0:
            return Decimal("0")

        commission = trade_value * Decimal(str(commission_rate))

        if min_commission > 0 and commission < min_commission:
            return min_commission

        return commission

    def _apply_slippage(
        self,
        *,
        raw_price: Decimal,
        action: str,
        slippage_rate: float,
    ) -> tuple[Decimal, Decimal, BacktestExecutionPriceType]:
        if raw_price <= 0:
            return raw_price, Decimal("0"), "next_open"

        if slippage_rate <= 0:
            return raw_price, Decimal("0"), "next_open"

        rate = Decimal(str(slippage_rate))

        if action == "buy":
            execution_price = raw_price * (Decimal("1") + rate)
            slippage_amount = execution_price - raw_price
            return execution_price, slippage_amount, "next_open_with_slippage"

        if action == "sell":
            execution_price = raw_price * (Decimal("1") - rate)
            slippage_amount = raw_price - execution_price
            return execution_price, slippage_amount, "next_open_with_slippage"

        return raw_price, Decimal("0"), "next_open"

    def _apply_stop_loss_decision(
        self,
        *,
        request: BacktestRequest,
        snapshot: BacktestSignalSnapshot,
        position_quantity: int,
        open_buy_trade: BacktestTrade | None,
    ) -> BacktestSignalSnapshot:
        risk_control = request.risk_control

        if not risk_control.enable_stop_loss:
            return snapshot

        if risk_control.stop_loss_rate is None:
            return snapshot

        if position_quantity <= 0:
            return snapshot

        if open_buy_trade is None:
            return snapshot

        stop_loss_price = open_buy_trade.price * (
            Decimal("1") - Decimal(str(risk_control.stop_loss_rate))
        )

        if snapshot.close_price > stop_loss_price:
            return snapshot

        warnings = [
            *snapshot.warnings,
            (
                "当前持仓已触发止损规则："
                f"买入成交价 {open_buy_trade.price}，"
                f"止损触发价 {stop_loss_price}，"
                f"当前收盘价 {snapshot.close_price}。"
            ),
        ]

        return snapshot.model_copy(
            update={
                "decision": "stop_loss",
                "risk_rule": "stop_loss",
                "risk_triggered": True,
                "reason": (
                    "当前持仓触发止损规则，"
                    f"收盘价 {snapshot.close_price} 已低于或等于止损触发价 "
                    f"{stop_loss_price}，将在下一交易日开盘价模拟卖出。"
                ),
                "warnings": warnings[:10],
            }
        )

    def _apply_take_profit_decision(
        self,
        *,
        request: BacktestRequest,
        snapshot: BacktestSignalSnapshot,
        position_quantity: int,
        open_buy_trade: BacktestTrade | None,
    ) -> BacktestSignalSnapshot:
        if snapshot.decision == "stop_loss":
            return snapshot

        risk_control = request.risk_control

        if not risk_control.enable_take_profit:
            return snapshot

        if risk_control.take_profit_rate is None:
            return snapshot

        if position_quantity <= 0:
            return snapshot

        if open_buy_trade is None:
            return snapshot

        take_profit_price = open_buy_trade.price * (
            Decimal("1") + Decimal(str(risk_control.take_profit_rate))
        )

        if snapshot.close_price < take_profit_price:
            return snapshot

        warnings = [
            *snapshot.warnings,
            (
                "当前持仓已触发止盈规则："
                f"买入成交价 {open_buy_trade.price}，"
                f"止盈触发价 {take_profit_price}，"
                f"当前收盘价 {snapshot.close_price}。"
            ),
        ]

        return snapshot.model_copy(
            update={
                "decision": "take_profit",
                "risk_rule": "take_profit",
                "risk_triggered": True,
                "reason": (
                    "当前持仓触发止盈规则，"
                    f"收盘价 {snapshot.close_price} 已高于或等于止盈触发价 "
                    f"{take_profit_price}，将在下一交易日开盘价模拟卖出。"
                ),
                "warnings": warnings[:10],
            }
        )

    def _apply_drawdown_guard_decision(
        self,
        *,
        request: BacktestRequest,
        snapshot: BacktestSignalSnapshot,
        position_quantity: int,
        current_drawdown: float,
    ) -> BacktestSignalSnapshot:
        risk_control = request.risk_control

        if not risk_control.enable_max_drawdown_guard:
            return snapshot.model_copy(
                update={
                    "current_drawdown": current_drawdown,
                }
            )

        if risk_control.max_drawdown_guard_rate is None:
            return snapshot.model_copy(
                update={
                    "current_drawdown": current_drawdown,
                }
            )

        if position_quantity > 0:
            return snapshot.model_copy(
                update={
                    "current_drawdown": current_drawdown,
                }
            )

        if current_drawdown < risk_control.max_drawdown_guard_rate:
            return snapshot.model_copy(
                update={
                    "current_drawdown": current_drawdown,
                }
            )

        if snapshot.decision != "buy":
            return snapshot.model_copy(
                update={
                    "current_drawdown": current_drawdown,
                }
            )

        warnings = [
            *snapshot.warnings,
            (
                "当前账户回撤已触发最大回撤保护："
                f"当前回撤 {current_drawdown:.2%}，"
                f"保护阈值 {risk_control.max_drawdown_guard_rate:.2%}，"
                "本次 buy 信号暂不执行。"
            ),
        ]

        return snapshot.model_copy(
            update={
                "decision": "drawdown_guard",
                "risk_rule": "drawdown_guard",
                "risk_triggered": True,
                "current_drawdown": current_drawdown,
                "reason": (
                    "当前账户权益回撤已触发最大回撤保护，"
                    f"当前回撤 {current_drawdown:.2%}，"
                    f"保护阈值 {risk_control.max_drawdown_guard_rate:.2%}，"
                    "虽然策略出现 buy 信号，但本交易日跳过买入。"
                ),
                "warnings": warnings[:10],
            }
        )

    def _apply_cooldown_decision(
        self,
        *,
        request: BacktestRequest,
        snapshot: BacktestSignalSnapshot,
        position_quantity: int,
        cooldown_days_left: int,
    ) -> BacktestSignalSnapshot:
        if snapshot.decision == "drawdown_guard":
            return snapshot

        risk_control = request.risk_control

        if not risk_control.enable_cooldown:
            return snapshot

        if risk_control.cooldown_days <= 0:
            return snapshot

        if position_quantity > 0:
            return snapshot

        if cooldown_days_left <= 0:
            return snapshot

        if snapshot.decision != "buy":
            return snapshot.model_copy(
                update={
                    "cooldown_days_left": cooldown_days_left,
                }
            )

        warnings = [
            *snapshot.warnings,
            (
                "当前仍处于冷却期，"
                f"剩余 {cooldown_days_left} 个交易日，"
                "本次 buy 信号暂不执行。"
            ),
        ]

        return snapshot.model_copy(
            update={
                "decision": "cooldown",
                "risk_rule": "cooldown",
                "risk_triggered": True,
                "cooldown_days_left": cooldown_days_left,
                "reason": (
                    "当前处于卖出后的冷却期，"
                    f"剩余 {cooldown_days_left} 个交易日，"
                    "虽然策略出现 buy 信号，但本交易日跳过买入。"
                ),
                "warnings": warnings[:10],
            }
        )

    def _build_trade_reason(
        self,
        *,
        snapshot: BacktestSignalSnapshot,
        execution_date,
    ) -> str:
        return (
            f"{snapshot.trade_date} 生成 {snapshot.decision} 信号，"
            f"于 {execution_date} 按下一根 K 线开盘价模拟成交；"
            "本回测已根据配置计算手续费和滑点。"
        )

