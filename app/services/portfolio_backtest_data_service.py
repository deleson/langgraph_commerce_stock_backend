"""组合回测数据读取与对齐服务。

组合回测不是简单把多只股票分别回测后相加，而是需要在同一批交易日上同时估值。
本服务负责读取每个资产的 K 线，并求出所有资产共同存在的交易日，供组合权益、
调仓和持仓快照使用。
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.market_candle import MarketCandle
from app.repositories.market_repo import AsyncMarketRepository
from app.schemas.portfolio_backtest import (
    PortfolioBacktestInputSnapshot,
    PortfolioBacktestRequest,
)


@dataclass(frozen=True)
class PortfolioBacktestCandleData:
    """组合回测的数据包。

    candles_by_symbol 保存每个资产的 K 线；common_trade_dates 是所有资产共有的
    交易日；input_snapshot 和 warnings 用于复盘本次组合回测输入。
    """

    candles_by_symbol: dict[str, list[MarketCandle]]
    common_trade_dates: list[date]
    input_snapshot: PortfolioBacktestInputSnapshot
    warnings: list[str]


class PortfolioBacktestDataService:
    """为组合回测读取并对齐多资产 K 线。"""

    def __init__(
        self,
        db: AsyncSession,
        *,
        repository: AsyncMarketRepository | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or AsyncMarketRepository(db)

    async def get_candles_for_portfolio_backtest(
        self,
        request: PortfolioBacktestRequest,
    ) -> PortfolioBacktestCandleData:
        """读取组合内所有资产 K 线，并计算共同交易日。

        source / adjust_type 必须保持一致，避免不同数据口径的资产被放进同一次
        组合回测中比较。
        """

        start_at = self._date_to_start_datetime(request.start_date)
        end_at = self._date_to_end_datetime(request.end_date)

        candles_by_symbol: dict[str, list[MarketCandle]] = {}

        for asset in request.assets:
            symbol_key = self._build_symbol_key(
                market=asset.market,
                symbol=asset.symbol,
            )
            candles = await self.repository.list_candles_by_date_range(
                symbol=asset.symbol,
                market=asset.market,
                timeframe=request.timeframe,
                start_at=start_at,
                end_at=end_at,
                adjust_type=request.adjust_type,
                source=request.source,
            )

            if not candles:
                raise NotFoundException(
                    message=(
                        "market candles not found for portfolio backtest, "
                        f"asset={symbol_key}, "
                        f"from {request.start_date} to {request.end_date}"
                    )
                )

            if len(candles) < request.min_required_candles:
                raise BadRequestException(
                    message=(
                        "not enough candles for portfolio backtest, "
                        f"asset={symbol_key}, "
                        f"required={request.min_required_candles}, "
                        f"actual={len(candles)}"
                    )
                )

            candles_by_symbol[symbol_key] = self._sort_by_time(candles)

        common_trade_dates = self._build_common_trade_dates(candles_by_symbol)

        if not common_trade_dates:
            raise BadRequestException(
                message=(
                    "no common trade dates found for portfolio backtest assets "
                    f"from {request.start_date} to {request.end_date}"
                )
            )

        if len(common_trade_dates) < request.min_required_candles:
            raise BadRequestException(
                message=(
                    "not enough common trade dates for portfolio backtest, "
                    f"required={request.min_required_candles}, "
                    f"actual={len(common_trade_dates)}"
                )
            )

        return PortfolioBacktestCandleData(
            candles_by_symbol=candles_by_symbol,
            common_trade_dates=common_trade_dates,
            input_snapshot=self._build_input_snapshot(
                request=request,
                candles_by_symbol=candles_by_symbol,
                common_trade_dates=common_trade_dates,
            ),
            warnings=self._build_warnings(
                request=request,
                candles_by_symbol=candles_by_symbol,
                common_trade_dates=common_trade_dates,
            ),
        )

    def _build_common_trade_dates(
        self,
        candles_by_symbol: dict[str, list[MarketCandle]],
    ) -> list[date]:
        """计算所有资产共同存在的交易日。

        组合权益必须在同一天同时知道每只资产价格；如果某只资产缺少该日期价格，
        第一版会跳过这个日期，避免估值失真。
        """

        date_sets: list[set[date]] = []

        for candles in candles_by_symbol.values():
            date_sets.append({candle.candle_time.date() for candle in candles})

        if not date_sets:
            return []

        common_dates = set.intersection(*date_sets)
        return sorted(common_dates)

    def _build_input_snapshot(
        self,
        *,
        request: PortfolioBacktestRequest,
        candles_by_symbol: dict[str, list[MarketCandle]],
        common_trade_dates: list[date],
    ) -> PortfolioBacktestInputSnapshot:
        candle_count_by_symbol = {
            symbol_key: len(candles)
            for symbol_key, candles in candles_by_symbol.items()
        }

        target_weights = {
            self._build_symbol_key(
                market=asset.market,
                symbol=asset.symbol,
            ): asset.target_weight
            for asset in request.assets
        }

        source = request.source
        if source is None:
            for candles in candles_by_symbol.values():
                if candles:
                    source = candles[-1].source
                    break

        return PortfolioBacktestInputSnapshot(
            asset_count=len(request.assets),
            candle_count_by_symbol=candle_count_by_symbol,
            first_trade_date=common_trade_dates[0],
            last_trade_date=common_trade_dates[-1],
            timeframe=request.timeframe,
            adjust_type=request.adjust_type,
            source=source,
            min_required_candles=request.min_required_candles,
            cash_deploy_ratio=request.cash_deploy_ratio,
            rebalance_frequency=request.rebalance_frequency,
            rebalance_interval_days=request.rebalance_interval_days,
            target_weights=target_weights,
            risk_control=request.risk_control,
        )

    def _build_warnings(
        self,
        *,
        request: PortfolioBacktestRequest,
        candles_by_symbol: dict[str, list[MarketCandle]],
        common_trade_dates: list[date],
    ) -> list[str]:
        warnings: list[str] = []

        first_common_date = common_trade_dates[0]
        last_common_date = common_trade_dates[-1]

        if first_common_date > request.start_date:
            warnings.append(
                "组合回测共同交易日的第一天晚于请求开始日期，回测将从共同可用数据开始。"
            )

        if last_common_date < request.end_date:
            warnings.append(
                "组合回测共同交易日的最后一天早于请求结束日期，回测将以共同可用数据结束。"
            )

        for symbol_key, candles in candles_by_symbol.items():
            first_candle_date = candles[0].candle_time.date()
            last_candle_date = candles[-1].candle_time.date()

            if first_candle_date > request.start_date:
                warnings.append(
                    f"{symbol_key} 的第一根 K 线晚于请求开始日期。"
                )

            if last_candle_date < request.end_date:
                warnings.append(
                    f"{symbol_key} 的最后一根 K 线早于请求结束日期。"
                )

        if request.timeframe != "1d":
            warnings.append(
                "阶段六点三第一版主要面向日 K 组合回测，非日 K 结果需要谨慎解读。"
            )

        if len(common_trade_dates) < min(
            len(candles) for candles in candles_by_symbol.values()
        ):
            warnings.append(
                "组合回测第一版使用所有股票共同交易日，个别股票缺失日期会被整体跳过。"
            )

        return warnings[:20]

    def _sort_by_time(
        self,
        candles: list[MarketCandle],
    ) -> list[MarketCandle]:
        """按时间升序返回 K 线，保证组合回测逐日推进。"""

        return sorted(candles, key=lambda candle: candle.candle_time)

    def _date_to_start_datetime(
        self,
        value,
    ) -> datetime:
        return datetime.combine(value, time.min, tzinfo=UTC)

    def _date_to_end_datetime(
        self,
        value,
    ) -> datetime:
        return datetime.combine(value, time.max, tzinfo=UTC)

    def _build_symbol_key(
        self,
        *,
        market: str,
        symbol: str,
    ) -> str:
        return f"{market}:{symbol.strip().upper()}"
