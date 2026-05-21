from decimal import Decimal

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
        )
        metrics = self._build_initial_metrics(
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
    ) -> list[PortfolioBacktestDailyEquity]:
        daily_equity: list[PortfolioBacktestDailyEquity] = []
        previous_total_equity: Decimal | None = None
        equity_high_watermark = request.initial_cash

        for trade_date in data.common_trade_dates:
            positions = self._build_position_snapshots(
                request=request,
                trade_date=trade_date,
                candle_by_symbol_and_date=candle_by_symbol_and_date,
                positions_by_symbol=positions_by_symbol,
                entry_price_by_symbol=entry_price_by_symbol,
                portfolio_cash=cash,
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
        portfolio_cash: Decimal,
    ) -> list[PortfolioBacktestPositionSnapshot]:
        positions: list[PortfolioBacktestPositionSnapshot] = []

        for asset in request.assets:
            symbol_key = self._build_symbol_key(
                market=asset.market,
                symbol=asset.symbol,
            )
            candle = candle_by_symbol_and_date[symbol_key][trade_date]
            quantity = positions_by_symbol.get(symbol_key, 0)
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

    def _build_initial_metrics(
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
        daily_returns = [
            item.daily_return
            for item in daily_equity
            if item.daily_return is not None
        ]

        return PortfolioBacktestMetrics(
            initial_cash=request.initial_cash,
            final_equity=final_equity,
            total_return=self._calculate_total_return(
                initial_cash=request.initial_cash,
                final_equity=final_equity,
            ),
            annualized_return=None,
            average_daily_return=self._calculate_average_daily_return(daily_returns),
            max_drawdown=max((item.drawdown for item in daily_equity), default=0),
            daily_return_volatility=None,
            annualized_volatility=None,
            sharpe_ratio=None,
            return_drawdown_ratio=None,
            trade_count=len(trades),
            buy_count=sum(1 for trade in trades if trade.action == "buy"),
            sell_count=sum(1 for trade in trades if trade.action == "sell"),
            rebalance_count=0,
            total_commission=Decimal("0"),
            total_slippage_cost=Decimal("0"),
            average_cash_ratio=1.0 if daily_equity else None,
            average_position_ratio=0.0 if daily_equity else None,
            turnover_rate=0.0,
            best_day_return=max(daily_returns) if daily_returns else None,
            worst_day_return=min(daily_returns) if daily_returns else None,
        )

    def _build_summary(
        self,
        *,
        request: PortfolioBacktestRequest,
        data: PortfolioBacktestCandleData,
        metrics: PortfolioBacktestMetrics,
    ) -> str:
        return (
            "阶段六点三组合回测已完成目标权重初始建仓。"
            f"本次组合包含 {len(request.assets)} 只股票，"
            f"共同交易日 {len(data.common_trade_dates)} 个，"
            f"初始资金 {self._format_decimal(request.initial_cash)}，"
            f"最终权益 {self._format_decimal(metrics.final_equity)}，"
            f"总收益率 {self._format_percent(metrics.total_return)}，"
            f"交易次数 {metrics.trade_count} 次。"
            "当前步骤尚未实现调仓、手续费、滑点和组合风控，"
            "因此结果主要反映初始权重买入后的持有表现。"
        )

    def _build_initial_warnings(
        self,
        *,
        request: PortfolioBacktestRequest,
        trades: list[PortfolioBacktestTrade],
    ) -> list[str]:
        warnings = [
            "阶段六点三步骤六已按目标权重完成初始建仓，但尚未执行调仓。",
            "当前买入数量按整数股计算，买不满目标权重的资金会保留为现金。",
            "当前初始建仓暂未计算手续费和滑点，步骤十会接入交易成本。",
            "本组合回测仅基于历史行情和规则模拟，不构成投资建议，也不代表未来收益。",
        ]

        if not trades:
            warnings.append(
                "本次组合回测没有生成初始建仓交易，可能是股票价格过高或可投入资金不足。"
            )

        if request.rebalance_frequency != "none":
            warnings.append(
                "调仓频率参数已记录，但步骤六尚未执行调仓逻辑。"
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

    def _build_symbol_key(
        self,
        *,
        market: str,
        symbol: str,
    ) -> str:
        return f"{market}:{symbol.strip().upper()}"