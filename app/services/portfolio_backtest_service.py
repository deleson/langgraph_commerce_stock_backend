from decimal import Decimal
import math

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_candle import MarketCandle
from app.schemas.portfolio_backtest import (
    PortfolioBacktestDailyEquity,
    PortfolioBacktestMetrics,
    PortfolioBacktestPositionSnapshot,
    PortfolioBacktestRequest,
    PortfolioBacktestResponse,
    PortfolioBacktestTrade,
)
from app.services.portfolio_backtest_data_service import (
    PortfolioBacktestCandleData,
    PortfolioBacktestDataService,
)


class PortfolioBacktestService:
    """Run portfolio backtests with shared cash and multi-asset equity snapshots."""
    TRADING_DAYS_PER_YEAR = 252

    def __init__(
        self,
        db: AsyncSession,
        *,
        data_service: PortfolioBacktestDataService | None = None,
    ) -> None:
        self.db = db
        self.data_service = data_service or PortfolioBacktestDataService(db)

    async def run_portfolio_backtest(
        self,
        request: PortfolioBacktestRequest,
    ) -> PortfolioBacktestResponse:
        data = await self.data_service.get_candles_for_portfolio_backtest(request)

        candle_by_symbol_and_date = self._build_candle_by_symbol_and_date(
            data.candles_by_symbol
        )

        portfolio_state = self._build_initial_portfolio_state(
            request=request,
            data=data,
            candle_by_symbol_and_date=candle_by_symbol_and_date,
        )

        trades = portfolio_state["trades"]
        daily_equity = self._build_daily_equity(
            request=request,
            data=data,
            candle_by_symbol_and_date=candle_by_symbol_and_date,
            cash=portfolio_state["cash"],
            positions_by_symbol=portfolio_state["positions_by_symbol"],
            entry_price_by_symbol=portfolio_state["entry_price_by_symbol"],
            trades=trades,
        )
        metrics = self._build_metrics(
            request=request,
            daily_equity=daily_equity,
            trades=trades,
        )

        return PortfolioBacktestResponse(
            assets=request.assets,
            start_date=request.start_date,
            end_date=request.end_date,
            status="available",
            unavailable_reason=None,
            summary=self._build_summary(
                request=request,
                data=data,
                metrics=metrics,
            ),
            metrics=metrics,
            trades=trades if request.include_trades else [],
            daily_equity=daily_equity if request.include_daily_equity else [],
            input_snapshot=data.input_snapshot,
            warnings=[
                *data.warnings,
                *self._build_initial_warnings(
                    request=request,
                    trades=trades,
                ),
            ],
        )

    def _build_candle_by_symbol_and_date(
        self,
        candles_by_symbol: dict[str, list[MarketCandle]],
    ) -> dict[str, dict]:
        return {
            symbol_key: {
                candle.candle_time.date(): candle
                for candle in candles
            }
            for symbol_key, candles in candles_by_symbol.items()
        }

    def _build_initial_portfolio_state(
        self,
        *,
        request: PortfolioBacktestRequest,
        data: PortfolioBacktestCandleData,
        candle_by_symbol_and_date: dict[str, dict],
    ) -> dict:
        first_trade_date = data.common_trade_dates[0]
        cash = request.initial_cash
        deploy_cash = request.initial_cash * Decimal(str(request.cash_deploy_ratio))

        positions_by_symbol: dict[str, int] = {}
        entry_price_by_symbol: dict[str, Decimal] = {}
        trades: list[PortfolioBacktestTrade] = []

        for asset in request.assets:
            symbol_key = self._build_symbol_key(
                market=asset.market,
                symbol=asset.symbol,
            )
            candle = candle_by_symbol_and_date[symbol_key][first_trade_date]
            open_price = candle.open

            positions_by_symbol[symbol_key] = 0

            if open_price <= 0:
                continue

            target_cash = deploy_cash * asset.target_weight
            quantity = int(target_cash // open_price)

            if quantity <= 0:
                continue

            trade_value = open_price * Decimal(quantity)

            if trade_value > cash:
                quantity = int(cash // open_price)
                trade_value = open_price * Decimal(quantity)

            if quantity <= 0:
                continue

            cash_before = cash
            cash = cash - trade_value
            positions_by_symbol[symbol_key] = quantity
            entry_price_by_symbol[symbol_key] = open_price

            trades.append(
                PortfolioBacktestTrade(
                    sequence_no=len(trades) + 1,
                    symbol=asset.symbol,
                    market=asset.market,
                    action="buy",
                    reason="initial_build",
                    trade_date=first_trade_date,
                    price=open_price,
                    quantity=quantity,
                    raw_price=open_price,
                    execution_price_type="next_open",
                    trade_value=trade_value,
                    commission=Decimal("0"),
                    slippage_amount=Decimal("0"),
                    slippage_cost=Decimal("0"),
                    cash_before=cash_before,
                    cash_after=cash,
                    position_before=0,
                    position_after=quantity,
                    target_weight=asset.target_weight,
                    actual_weight_before=Decimal("0"),
                    actual_weight_after=None,
                    portfolio_equity_after=request.initial_cash,
                )
            )

        return {
            "cash": cash,
            "positions_by_symbol": positions_by_symbol,
            "entry_price_by_symbol": entry_price_by_symbol,
            "trades": trades,
        }

    def _build_daily_equity(
        self,
        *,
        request: PortfolioBacktestRequest,
        data: PortfolioBacktestCandleData,
        candle_by_symbol_and_date: dict[str, dict],
        cash: Decimal,
        positions_by_symbol: dict[str, int],
        entry_price_by_symbol: dict[str, Decimal],
        trades: list[PortfolioBacktestTrade],
    ) -> list[PortfolioBacktestDailyEquity]:
        daily_equity: list[PortfolioBacktestDailyEquity] = []
        previous_total_equity: Decimal | None = None
        equity_high_watermark = request.initial_cash

        for trade_day_index, trade_date in enumerate(data.common_trade_dates):
            positions = self._build_position_snapshots(
                request=request,
                trade_date=trade_date,
                candle_by_symbol_and_date=candle_by_symbol_and_date,
                positions_by_symbol=positions_by_symbol,
                entry_price_by_symbol=entry_price_by_symbol,
            )
            position_market_value = sum(
                (position.market_value for position in positions),
                Decimal("0"),
            )
            total_equity = cash + position_market_value

            positions = self._rebuild_positions_with_actual_weight(
                positions=positions,
                total_equity=total_equity,
            )

            daily_return = self._calculate_daily_return(
                total_equity=total_equity,
                previous_total_equity=previous_total_equity,
            )

            if total_equity > equity_high_watermark:
                equity_high_watermark = total_equity

            drawdown = self._calculate_drawdown(
                total_equity=total_equity,
                equity_high_watermark=equity_high_watermark,
            )

            daily_equity.append(
                PortfolioBacktestDailyEquity(
                    trade_date=trade_date,
                    cash=cash,
                    position_market_value=position_market_value,
                    total_equity=total_equity,
                    daily_return=daily_return,
                    drawdown=drawdown,
                    positions=positions if request.include_position_snapshots else [],
                )
            )

            if self._should_rebalance(
                request=request,
                trade_day_index=trade_day_index,
                common_trade_dates=data.common_trade_dates,
            ):
                next_trade_date = data.common_trade_dates[trade_day_index + 1]
                current_values_by_symbol = self._build_current_values_by_symbol(
                    positions=positions,
                )
                cash = self._execute_rebalance(
                    request=request,
                    execution_date=next_trade_date,
                    portfolio_equity=total_equity,
                    current_values_by_symbol=current_values_by_symbol,
                    cash=cash,
                    positions_by_symbol=positions_by_symbol,
                    entry_price_by_symbol=entry_price_by_symbol,
                    candle_by_symbol_and_date=candle_by_symbol_and_date,
                    trades=trades,
                )

            previous_total_equity = total_equity

        return daily_equity
    def _build_position_snapshots(
        self,
        *,
        request: PortfolioBacktestRequest,
        trade_date,
        candle_by_symbol_and_date: dict[str, dict],
        positions_by_symbol: dict[str, int],
        entry_price_by_symbol: dict[str, Decimal],
    ) -> list[PortfolioBacktestPositionSnapshot]:
        positions: list[PortfolioBacktestPositionSnapshot] = []

        for asset in request.assets:
            symbol_key = self._build_symbol_key(
                market=asset.market,
                symbol=asset.symbol,
            )
            candle = candle_by_symbol_and_date[symbol_key][trade_date]
            quantity = positions_by_symbol.get(symbol_key, 0)
            # Daily position snapshots use close price because daily equity is marked at close.
            market_value = candle.close * Decimal(quantity)
            entry_price = entry_price_by_symbol.get(symbol_key)

            unrealized_pnl: Decimal | None = None
            unrealized_return: float | None = None

            if entry_price is not None and quantity > 0:
                cost = entry_price * Decimal(quantity)
                unrealized_pnl = market_value - cost
                if cost > 0:
                    unrealized_return = float(unrealized_pnl / cost)

            positions.append(
                PortfolioBacktestPositionSnapshot(
                    symbol=asset.symbol,
                    market=asset.market,
                    quantity=quantity,
                    close_price=candle.close,
                    market_value=market_value,
                    target_weight=asset.target_weight,
                    actual_weight=Decimal("0"),
                    unrealized_pnl=unrealized_pnl,
                    unrealized_return=unrealized_return,
                )
            )

        return positions

    def _rebuild_positions_with_actual_weight(
        self,
        *,
        positions: list[PortfolioBacktestPositionSnapshot],
        total_equity: Decimal,
    ) -> list[PortfolioBacktestPositionSnapshot]:
        if total_equity <= 0:
            return positions

        rebuilt_positions: list[PortfolioBacktestPositionSnapshot] = []

        for position in positions:
            rebuilt_positions.append(
                position.model_copy(
                    update={
                        "actual_weight": position.market_value / total_equity,
                    }
                )
            )

        return rebuilt_positions

    def _should_rebalance(
        self,
        *,
        request: PortfolioBacktestRequest,
        trade_day_index: int,
        common_trade_dates,
    ) -> bool:
        if request.rebalance_frequency == "none":
            return False

        if trade_day_index >= len(common_trade_dates) - 1:
            return False

        if request.rebalance_frequency == "daily":
            return True

        if request.rebalance_frequency == "weekly":
            return (trade_day_index + 1) % 5 == 0

        if request.rebalance_frequency == "monthly":
            return (trade_day_index + 1) % 20 == 0

        if request.rebalance_frequency == "interval":
            interval_days = request.rebalance_interval_days
            if interval_days is None or interval_days <= 0:
                return False
            return (trade_day_index + 1) % interval_days == 0

        return False

    def _build_current_values_by_symbol(
        self,
        *,
        positions: list[PortfolioBacktestPositionSnapshot],
    ) -> dict[str, Decimal]:
        return {
            self._build_symbol_key(
                market=position.market,
                symbol=position.symbol,
            ): position.market_value
            for position in positions
        }

    def _calculate_portfolio_market_value(
        self,
        *,
        execution_date,
        positions_by_symbol: dict[str, int],
        candle_by_symbol_and_date: dict[str, dict],
    ) -> Decimal:
        market_value = Decimal("0")

        for symbol_key, quantity in positions_by_symbol.items():
            if quantity <= 0:
                continue

            candle = candle_by_symbol_and_date[symbol_key][execution_date]
            market_value += candle.open * Decimal(quantity)

        return market_value

    def _calculate_weighted_average_entry_price(
        self,
        *,
        current_quantity: int,
        current_entry_price: Decimal | None,
        buy_quantity: int,
        buy_price: Decimal,
    ) -> Decimal:
        if current_quantity <= 0 or current_entry_price is None:
            return buy_price

        total_quantity = current_quantity + buy_quantity

        if total_quantity <= 0:
            return buy_price

        current_cost = current_entry_price * Decimal(current_quantity)
        new_cost = buy_price * Decimal(buy_quantity)

        return (current_cost + new_cost) / Decimal(total_quantity)

    def _calculate_actual_weight_after_trade(
        self,
        *,
        symbol_key: str,
        execution_date,
        cash: Decimal,
        positions_by_symbol: dict[str, int],
        candle_by_symbol_and_date: dict[str, dict],
    ) -> Decimal | None:
        position_market_value = self._calculate_portfolio_market_value(
            execution_date=execution_date,
            positions_by_symbol=positions_by_symbol,
            candle_by_symbol_and_date=candle_by_symbol_and_date,
        )
        total_equity = cash + position_market_value

        if total_equity <= 0:
            return None

        candle = candle_by_symbol_and_date[symbol_key][execution_date]
        symbol_value = candle.open * Decimal(positions_by_symbol.get(symbol_key, 0))

        return symbol_value / total_equity

    def _execute_rebalance(
        self,
        *,
        request: PortfolioBacktestRequest,
        execution_date,
        portfolio_equity: Decimal,
        current_values_by_symbol: dict[str, Decimal],
        cash: Decimal,
        positions_by_symbol: dict[str, int],
        entry_price_by_symbol: dict[str, Decimal],
        candle_by_symbol_and_date: dict[str, dict],
        trades: list[PortfolioBacktestTrade],
    ) -> Decimal:
        target_values = self._build_target_values(
            request=request,
            portfolio_equity=portfolio_equity,
        )

        cash = self._execute_rebalance_sells(
            request=request,
            execution_date=execution_date,
            target_values=target_values,
            current_values_by_symbol=current_values_by_symbol,
            cash=cash,
            positions_by_symbol=positions_by_symbol,
            entry_price_by_symbol=entry_price_by_symbol,
            candle_by_symbol_and_date=candle_by_symbol_and_date,
            trades=trades,
        )

        cash = self._execute_rebalance_buys(
            request=request,
            execution_date=execution_date,
            target_values=target_values,
            current_values_by_symbol=current_values_by_symbol,
            cash=cash,
            positions_by_symbol=positions_by_symbol,
            entry_price_by_symbol=entry_price_by_symbol,
            candle_by_symbol_and_date=candle_by_symbol_and_date,
            trades=trades,
        )

        return cash

    def _build_target_values(
        self,
        *,
        request: PortfolioBacktestRequest,
        portfolio_equity: Decimal,
    ) -> dict[str, Decimal]:
        target_values: dict[str, Decimal] = {}

        for asset in request.assets:
            symbol_key = self._build_symbol_key(
                market=asset.market,
                symbol=asset.symbol,
            )
            target_values[symbol_key] = portfolio_equity * asset.target_weight

        return target_values

    def _execute_rebalance_sells(
        self,
        *,
        request: PortfolioBacktestRequest,
        execution_date,
        target_values: dict[str, Decimal],
        current_values_by_symbol: dict[str, Decimal],
        cash: Decimal,
        positions_by_symbol: dict[str, int],
        entry_price_by_symbol: dict[str, Decimal],
        candle_by_symbol_and_date: dict[str, dict],
        trades: list[PortfolioBacktestTrade],
    ) -> Decimal:
        for asset in request.assets:
            symbol_key = self._build_symbol_key(
                market=asset.market,
                symbol=asset.symbol,
            )
            current_quantity = positions_by_symbol.get(symbol_key, 0)

            if current_quantity <= 0:
                continue

            current_value = current_values_by_symbol.get(symbol_key, Decimal("0"))
            target_value = target_values[symbol_key]

            if current_value <= target_value:
                continue

            execution_candle = candle_by_symbol_and_date[symbol_key][execution_date]
            execution_price = execution_candle.open

            if execution_price <= 0:
                continue

            value_to_sell = current_value - target_value
            quantity_to_sell = int(value_to_sell // execution_price)
            quantity_to_sell = min(quantity_to_sell, current_quantity)

            if quantity_to_sell <= 0:
                continue

            trade_value = execution_price * Decimal(quantity_to_sell)
            cash_before = cash
            position_before = current_quantity

            cash = cash + trade_value
            positions_by_symbol[symbol_key] = current_quantity - quantity_to_sell

            if positions_by_symbol[symbol_key] <= 0:
                entry_price_by_symbol.pop(symbol_key, None)

            portfolio_market_value_after = self._calculate_portfolio_market_value(
                execution_date=execution_date,
                positions_by_symbol=positions_by_symbol,
                candle_by_symbol_and_date=candle_by_symbol_and_date,
            )
            portfolio_equity_after = cash + portfolio_market_value_after
            actual_weight_after = self._calculate_actual_weight_after_trade(
                symbol_key=symbol_key,
                execution_date=execution_date,
                cash=cash,
                positions_by_symbol=positions_by_symbol,
                candle_by_symbol_and_date=candle_by_symbol_and_date,
            )

            trades.append(
                PortfolioBacktestTrade(
                    sequence_no=len(trades) + 1,
                    symbol=asset.symbol,
                    market=asset.market,
                    action="sell",
                    reason="rebalance",
                    trade_date=execution_date,
                    price=execution_price,
                    quantity=quantity_to_sell,
                    raw_price=execution_price,
                    execution_price_type="next_open",
                    trade_value=trade_value,
                    commission=Decimal("0"),
                    slippage_amount=Decimal("0"),
                    slippage_cost=Decimal("0"),
                    cash_before=cash_before,
                    cash_after=cash,
                    position_before=position_before,
                    position_after=positions_by_symbol[symbol_key],
                    target_weight=asset.target_weight,
                    actual_weight_before=None,
                    actual_weight_after=actual_weight_after,
                    portfolio_equity_after=portfolio_equity_after,
                )
            )

        return cash

    def _execute_rebalance_buys(
        self,
        *,
        request: PortfolioBacktestRequest,
        execution_date,
        target_values: dict[str, Decimal],
        current_values_by_symbol: dict[str, Decimal],
        cash: Decimal,
        positions_by_symbol: dict[str, int],
        entry_price_by_symbol: dict[str, Decimal],
        candle_by_symbol_and_date: dict[str, dict],
        trades: list[PortfolioBacktestTrade],
    ) -> Decimal:
        for asset in request.assets:
            symbol_key = self._build_symbol_key(
                market=asset.market,
                symbol=asset.symbol,
            )
            current_quantity = positions_by_symbol.get(symbol_key, 0)
            current_value = current_values_by_symbol.get(symbol_key, Decimal("0"))
            target_value = target_values[symbol_key]

            if current_value >= target_value:
                continue

            execution_candle = candle_by_symbol_and_date[symbol_key][execution_date]
            execution_price = execution_candle.open

            if execution_price <= 0:
                continue

            value_to_buy = target_value - current_value
            affordable_value = min(value_to_buy, cash)
            quantity_to_buy = int(affordable_value // execution_price)

            if quantity_to_buy <= 0:
                continue

            trade_value = execution_price * Decimal(quantity_to_buy)

            if trade_value > cash:
                quantity_to_buy = int(cash // execution_price)
                trade_value = execution_price * Decimal(quantity_to_buy)

            if quantity_to_buy <= 0:
                continue

            cash_before = cash
            position_before = current_quantity

            cash = cash - trade_value
            entry_price_by_symbol[symbol_key] = (
                self._calculate_weighted_average_entry_price(
                    current_quantity=current_quantity,
                    current_entry_price=entry_price_by_symbol.get(symbol_key),
                    buy_quantity=quantity_to_buy,
                    buy_price=execution_price,
                )
            )
            positions_by_symbol[symbol_key] = current_quantity + quantity_to_buy

            portfolio_market_value_after = self._calculate_portfolio_market_value(
                execution_date=execution_date,
                positions_by_symbol=positions_by_symbol,
                candle_by_symbol_and_date=candle_by_symbol_and_date,
            )
            portfolio_equity_after = cash + portfolio_market_value_after
            actual_weight_after = self._calculate_actual_weight_after_trade(
                symbol_key=symbol_key,
                execution_date=execution_date,
                cash=cash,
                positions_by_symbol=positions_by_symbol,
                candle_by_symbol_and_date=candle_by_symbol_and_date,
            )

            trades.append(
                PortfolioBacktestTrade(
                    sequence_no=len(trades) + 1,
                    symbol=asset.symbol,
                    market=asset.market,
                    action="buy",
                    reason="rebalance",
                    trade_date=execution_date,
                    price=execution_price,
                    quantity=quantity_to_buy,
                    raw_price=execution_price,
                    execution_price_type="next_open",
                    trade_value=trade_value,
                    commission=Decimal("0"),
                    slippage_amount=Decimal("0"),
                    slippage_cost=Decimal("0"),
                    cash_before=cash_before,
                    cash_after=cash,
                    position_before=position_before,
                    position_after=positions_by_symbol[symbol_key],
                    target_weight=asset.target_weight,
                    actual_weight_before=None,
                    actual_weight_after=actual_weight_after,
                    portfolio_equity_after=portfolio_equity_after,
                )
            )

        return cash

    def _build_metrics(
        self,
        *,
        request: PortfolioBacktestRequest,
        daily_equity: list[PortfolioBacktestDailyEquity],
        trades: list[PortfolioBacktestTrade],
    ) -> PortfolioBacktestMetrics:
        final_equity = (
            daily_equity[-1].total_equity
            if daily_equity
            else request.initial_cash
        )
        daily_returns = self._build_daily_returns(daily_equity)

        total_return = self._calculate_total_return(
            initial_cash=request.initial_cash,
            final_equity=final_equity,
        )
        average_daily_return = self._calculate_average_daily_return(daily_returns)
        max_drawdown = max((item.drawdown for item in daily_equity), default=0)

        daily_return_volatility = self._calculate_daily_return_volatility(
            daily_returns
        )
        annualized_volatility = self._calculate_annualized_volatility(
            daily_return_volatility
        )

        return PortfolioBacktestMetrics(
            initial_cash=request.initial_cash,
            final_equity=final_equity,
            total_return=total_return,
            annualized_return=self._calculate_annualized_return(
                initial_cash=request.initial_cash,
                final_equity=final_equity,
                trading_days=len(daily_equity),
            ),
            average_daily_return=average_daily_return,
            max_drawdown=max_drawdown,
            daily_return_volatility=daily_return_volatility,
            annualized_volatility=annualized_volatility,
            sharpe_ratio=self._calculate_sharpe_ratio(
                average_daily_return=average_daily_return,
                daily_return_volatility=daily_return_volatility,
            ),
            return_drawdown_ratio=self._calculate_return_drawdown_ratio(
                total_return=total_return,
                max_drawdown=max_drawdown,
            ),
            trade_count=len(trades),
            buy_count=sum(1 for trade in trades if trade.action == "buy"),
            sell_count=sum(1 for trade in trades if trade.action == "sell"),
            rebalance_count=len(
                {
                    trade.trade_date
                    for trade in trades
                    if trade.reason == "rebalance"
                }
            ),
            total_commission=Decimal("0"),
            total_slippage_cost=Decimal("0"),
            average_cash_ratio=self._calculate_average_cash_ratio(daily_equity),
            average_position_ratio=self._calculate_average_position_ratio(daily_equity),
            turnover_rate=self._calculate_turnover_rate(
                trades=trades,
                daily_equity=daily_equity,
            ),
            best_day_return=max(daily_returns) if daily_returns else None,
            worst_day_return=min(daily_returns) if daily_returns else None,
        )

    def _build_daily_returns(
        self,
        daily_equity: list[PortfolioBacktestDailyEquity],
    ) -> list[float]:
        return [
            item.daily_return
            for item in daily_equity
            if item.daily_return is not None
        ]

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

        return equity_ratio ** (self.TRADING_DAYS_PER_YEAR / trading_days) - 1

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

        return daily_return_volatility * math.sqrt(self.TRADING_DAYS_PER_YEAR)

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

        return (
            average_daily_return
            / daily_return_volatility
            * math.sqrt(self.TRADING_DAYS_PER_YEAR)
        )

    def _calculate_return_drawdown_ratio(
        self,
        *,
        total_return: float,
        max_drawdown: float,
    ) -> float | None:
        if max_drawdown <= 0:
            return None

        return total_return / max_drawdown

    def _calculate_turnover_rate(
        self,
        *,
        trades: list[PortfolioBacktestTrade],
        daily_equity: list[PortfolioBacktestDailyEquity],
    ) -> float | None:
        average_total_equity = self._calculate_average_total_equity(daily_equity)

        if average_total_equity is None or average_total_equity <= 0:
            return None

        rebalance_trade_value = sum(
            (
                trade.trade_value
                for trade in trades
                if trade.reason == "rebalance"
            ),
            Decimal("0"),
        )

        return float(rebalance_trade_value / average_total_equity)

    def _calculate_average_total_equity(
        self,
        daily_equity: list[PortfolioBacktestDailyEquity],
    ) -> Decimal | None:
        if not daily_equity:
            return None

        total_equity = sum(
            (item.total_equity for item in daily_equity),
            Decimal("0"),
        )

        return total_equity / Decimal(len(daily_equity))

    def _calculate_average_cash_ratio(
        self,
        daily_equity: list[PortfolioBacktestDailyEquity],
    ) -> float | None:
        ratios: list[float] = []

        for item in daily_equity:
            if item.total_equity > 0:
                ratios.append(float(item.cash / item.total_equity))

        if not ratios:
            return None

        return sum(ratios) / len(ratios)

    def _calculate_average_position_ratio(
        self,
        daily_equity: list[PortfolioBacktestDailyEquity],
    ) -> float | None:
        ratios: list[float] = []

        for item in daily_equity:
            if item.total_equity > 0:
                ratios.append(float(item.position_market_value / item.total_equity))

        if not ratios:
            return None

        return sum(ratios) / len(ratios)

    def _build_summary(
        self,
        *,
        request: PortfolioBacktestRequest,
        data: PortfolioBacktestCandleData,
        metrics: PortfolioBacktestMetrics,
    ) -> str:
        return (
            "阶段六点三组合回测已完成目标权重初始建仓、固定频率调仓、每日权益快照和组合绩效指标计算。"
            f"本次组合包含 {len(request.assets)} 只股票，"
            f"共同交易日 {len(data.common_trade_dates)} 个，"
            f"初始资金 {self._format_decimal(request.initial_cash)}，"
            f"最终权益 {self._format_decimal(metrics.final_equity)}，"
            f"总收益率 {self._format_percent(metrics.total_return)}，"
            f"年化收益率 {self._format_percent(metrics.annualized_return)}，"
            f"最大回撤 {self._format_percent(metrics.max_drawdown)}，"
            f"年化波动率 {self._format_percent(metrics.annualized_volatility)}，"
            f"夏普比率 {self._format_float(metrics.sharpe_ratio)}，"
            f"收益回撤比 {self._format_float(metrics.return_drawdown_ratio)}，"
            f"换手率 {self._format_percent(metrics.turnover_rate)}，"
            f"交易次数 {metrics.trade_count} 次，"
            f"调仓次数 {metrics.rebalance_count} 次。"
            "当前步骤仍未计算手续费、滑点和组合风控，"
            "因此组合绩效属于无交易成本版本。"
        )

    def _build_initial_warnings(
        self,
        *,
        request: PortfolioBacktestRequest,
        trades: list[PortfolioBacktestTrade],
    ) -> list[str]:
        warnings = [
            "阶段六点三步骤九已实现组合绩效指标计算。",
            "组合每日权益使用收盘价估算，调仓交易仍按 T 日收盘后判断、T+1 日开盘价执行。",
            "组合年化收益、年化波动率和夏普比率均按 252 个交易日估算。",
            "换手率第一版只统计调仓交易金额，不统计初始建仓金额。",
            "当前组合回测暂未计算手续费和滑点，步骤十会接入交易成本。",
            "本组合回测仅基于历史行情和规则模拟，不构成投资建议，也不代表未来收益。",
        ]

        if not trades:
            warnings.append(
                "本次组合回测没有生成初始建仓交易，可能是股票价格过高或可投入资金不足。"
            )

        if request.rebalance_frequency == "none":
            warnings.append(
                "本次组合回测设置为不调仓，仅保留初始建仓后的持有表现。"
            )

        return warnings

    def _calculate_total_return(
        self,
        *,
        initial_cash: Decimal,
        final_equity: Decimal,
    ) -> float:
        if initial_cash <= 0:
            return 0.0

        return float((final_equity - initial_cash) / initial_cash)

    def _calculate_daily_return(
        self,
        *,
        total_equity: Decimal,
        previous_total_equity: Decimal | None,
    ) -> float | None:
        if previous_total_equity is None or previous_total_equity <= 0:
            return None

        return float((total_equity - previous_total_equity) / previous_total_equity)

    def _calculate_average_daily_return(
        self,
        daily_returns: list[float],
    ) -> float | None:
        if not daily_returns:
            return None

        return sum(daily_returns) / len(daily_returns)

    def _calculate_drawdown(
        self,
        *,
        total_equity: Decimal,
        equity_high_watermark: Decimal,
    ) -> float:
        if equity_high_watermark <= 0:
            return 0.0

        if total_equity >= equity_high_watermark:
            return 0.0

        return float((equity_high_watermark - total_equity) / equity_high_watermark)

    def _format_decimal(
        self,
        value: Decimal,
    ) -> str:
        return f"{value:.2f}"

    def _format_percent(
        self,
        value: float | None,
    ) -> str:
        if value is None:
            return "不可计算"

        return f"{value:.2%}"

    def _format_float(
        self,
        value: float | None,
    ) -> str:
        if value is None:
            return "不可计算"

        return f"{value:.2f}"

    def _build_symbol_key(
        self,
        *,
        market: str,
        symbol: str,
    ) -> str:
        return f"{market}:{symbol.strip().upper()}"