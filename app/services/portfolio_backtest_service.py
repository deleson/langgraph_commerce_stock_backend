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

        trades: list[PortfolioBacktestTrade] = []
        daily_equity = self._build_initial_daily_equity(
            request=request,
            data=data,
            candle_by_symbol_and_date=candle_by_symbol_and_date,
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
                *self._build_initial_warnings(request),
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

    def _build_initial_daily_equity(
        self,
        *,
        request: PortfolioBacktestRequest,
        data: PortfolioBacktestCandleData,
        candle_by_symbol_and_date: dict[str, dict],
    ) -> list[PortfolioBacktestDailyEquity]:
        daily_equity: list[PortfolioBacktestDailyEquity] = []
        previous_total_equity: Decimal | None = None
        equity_high_watermark = request.initial_cash

        for trade_date in data.common_trade_dates:
            positions = self._build_empty_position_snapshots(
                request=request,
                trade_date=trade_date,
                candle_by_symbol_and_date=candle_by_symbol_and_date,
            )
            position_market_value = Decimal("0")
            total_equity = request.initial_cash

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
                    cash=request.initial_cash,
                    position_market_value=position_market_value,
                    total_equity=total_equity,
                    daily_return=daily_return,
                    drawdown=drawdown,
                    positions=positions if request.include_position_snapshots else [],
                )
            )

            previous_total_equity = total_equity

        return daily_equity

    def _build_empty_position_snapshots(
        self,
        *,
        request: PortfolioBacktestRequest,
        trade_date,
        candle_by_symbol_and_date: dict[str, dict],
    ) -> list[PortfolioBacktestPositionSnapshot]:
        positions: list[PortfolioBacktestPositionSnapshot] = []

        for asset in request.assets:
            symbol_key = self._build_symbol_key(
                market=asset.market,
                symbol=asset.symbol,
            )
            candle = candle_by_symbol_and_date[symbol_key][trade_date]

            positions.append(
                PortfolioBacktestPositionSnapshot(
                    symbol=asset.symbol,
                    market=asset.market,
                    quantity=0,
                    close_price=candle.close,
                    market_value=Decimal("0"),
                    target_weight=asset.target_weight,
                    actual_weight=Decimal("0"),
                    unrealized_pnl=None,
                    unrealized_return=None,
                )
            )

        return positions

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
            "阶段六点三组合回测引擎初版已完成数据读取和逐日权益框架。"
            f"本次组合包含 {len(request.assets)} 只股票，"
            f"共同交易日 {len(data.common_trade_dates)} 个，"
            f"初始资金 {self._format_decimal(request.initial_cash)}，"
            f"最终权益 {self._format_decimal(metrics.final_equity)}，"
            f"总收益率 {self._format_percent(metrics.total_return)}。"
            "当前步骤尚未实现初始建仓、调仓、手续费、滑点和组合风控，"
            "因此本步骤结果主要用于验证组合回测主流程。"
        )

    def _build_initial_warnings(
        self,
        request: PortfolioBacktestRequest,
    ) -> list[str]:
        warnings = [
            "阶段六点三步骤五仅创建组合回测引擎初版，尚未执行初始建仓。",
            "当前组合每日权益暂时保持为初始现金，步骤六会加入按目标权重建仓。",
            "当前组合交易列表暂为空，步骤七会加入调仓交易。",
            "本组合回测仅基于历史行情和规则模拟，不构成投资建议，也不代表未来收益。",
        ]

        if request.rebalance_frequency != "none":
            warnings.append(
                "调仓频率参数已记录，但步骤五尚未执行调仓逻辑。"
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