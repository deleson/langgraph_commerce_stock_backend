from __future__ import annotations

"""纸面交易权益快照服务。

本文件负责把账户现金和当前持仓市值汇总成权益曲线快照。
它不生成订单、不生成成交、不更新持仓，只做权益统计。
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_DOWN

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper_trading_account import PaperTradingAccount
from app.models.paper_trading_equity_snapshot import PaperTradingEquitySnapshot
from app.models.paper_trading_position import PaperTradingPosition
from app.repositories.paper_trading_repo import AsyncPaperTradingRepository
from app.schemas.paper_trading import (
    PaperTradingEquitySnapshotResponse,
    PaperTradingListQuery,
)


@dataclass(slots=True)
class PaperTradingEquityCalculation:
    """一次权益快照的计算结果。"""

    account_id: int
    snapshot_date: date
    cash_balance: Decimal
    position_market_value: Decimal
    total_equity: Decimal
    total_return: Decimal
    daily_return: Decimal | None
    max_drawdown: Decimal
    position_count: int
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PaperTradingEquitySnapshotResult:
    snapshot: PaperTradingEquitySnapshot
    calculation: PaperTradingEquityCalculation
    created: bool
    warnings: list[str] = field(default_factory=list)


class PaperTradingEquityService:
    """创建或更新纸面交易权益快照。

    total_equity = cash_balance + position_market_value。
    daily_return、total_return、max_drawdown 都基于虚拟账户权益曲线计算。
    """

    MONEY_PRECISION = Decimal("0.0001")
    RETURN_PRECISION = Decimal("0.00000001")
    POSITION_QUERY_LIMIT = 100
    HISTORY_QUERY_LIMIT = 100

    def __init__(
        self,
        db: AsyncSession,
        *,
        repository: AsyncPaperTradingRepository | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or AsyncPaperTradingRepository(db)

    async def create_or_update_snapshot(
        self,
        *,
        account: PaperTradingAccount,
        user_id: int,
        snapshot_date: date | None = None,
    ) -> PaperTradingEquitySnapshotResult:
        """创建或更新指定日期的权益快照。

        同一账户同一天只保留一条快照：如果已存在则更新，不存在则创建。
        这让 API 手动 tick 和后台定时 tick 重复执行时仍然保持幂等。
        """

        resolved_snapshot_date = snapshot_date or self._today()

        positions = await self.repository.list_positions(
            account_id=account.id,
            user_id=user_id,
            query=PaperTradingListQuery(
                limit=self.POSITION_QUERY_LIMIT,
                offset=0,
            ),
        )

        historical_snapshots = await self.repository.list_equity_snapshots(
            account_id=account.id,
            user_id=user_id,
            query=PaperTradingListQuery(
                limit=self.HISTORY_QUERY_LIMIT,
                offset=0,
            ),
        )

        calculation = self._calculate_equity(
            account=account,
            positions=positions,
            historical_snapshots=historical_snapshots,
            snapshot_date=resolved_snapshot_date,
        )

        existing_snapshot = await self.repository.get_equity_snapshot_by_date(
            account_id=account.id,
            snapshot_date=resolved_snapshot_date,
        )

        if existing_snapshot is None:
            snapshot = await self.repository.create_equity_snapshot(
                account_id=account.id,
                snapshot_date=resolved_snapshot_date,
                cash_balance=calculation.cash_balance,
                position_market_value=calculation.position_market_value,
                total_equity=calculation.total_equity,
                total_return=calculation.total_return,
                daily_return=calculation.daily_return,
                max_drawdown=calculation.max_drawdown,
            )
            created = True
        else:
            snapshot = await self.repository.update_equity_snapshot(
                snapshot=existing_snapshot,
                cash_balance=calculation.cash_balance,
                position_market_value=calculation.position_market_value,
                total_equity=calculation.total_equity,
                total_return=calculation.total_return,
                daily_return=calculation.daily_return,
                max_drawdown=calculation.max_drawdown,
            )
            created = False

        return PaperTradingEquitySnapshotResult(
            snapshot=snapshot,
            calculation=calculation,
            created=created,
            warnings=calculation.warnings,
        )

    async def get_latest_snapshot(
        self,
        *,
        account_id: int,
        user_id: int,
    ) -> PaperTradingEquitySnapshotResponse | None:
        snapshot = await self.repository.get_latest_equity_snapshot(
            account_id=account_id,
            user_id=user_id,
        )

        if snapshot is None:
            return None

        return self._build_snapshot_response(snapshot)

    def _calculate_equity(
        self,
        *,
        account: PaperTradingAccount,
        positions: list[PaperTradingPosition],
        historical_snapshots: list[PaperTradingEquitySnapshot],
        snapshot_date: date,
    ) -> PaperTradingEquityCalculation:
        """计算现金、持仓市值、总权益、收益率和最大回撤。"""

        warnings: list[str] = []

        cash_balance = self._quantize_money(self._to_decimal(account.cash_balance))
        position_market_value = self._sum_position_market_value(positions)
        total_equity = self._quantize_money(cash_balance + position_market_value)

        total_return = self._calculate_total_return(
            initial_cash=self._to_decimal(account.initial_cash),
            total_equity=total_equity,
        )

        previous_snapshot = self._find_previous_snapshot(
            historical_snapshots=historical_snapshots,
            snapshot_date=snapshot_date,
        )
        daily_return = self._calculate_daily_return(
            previous_snapshot=previous_snapshot,
            total_equity=total_equity,
        )

        max_drawdown = self._calculate_max_drawdown(
            historical_snapshots=historical_snapshots,
            snapshot_date=snapshot_date,
            total_equity=total_equity,
        )

        if len(positions) >= self.POSITION_QUERY_LIMIT:
            warnings.append(
                f"本次权益快照最多汇总 {self.POSITION_QUERY_LIMIT} 条持仓记录，"
                "如果账户持仓超过该数量，后续需要扩展分页汇总。"
            )

        return PaperTradingEquityCalculation(
            account_id=account.id,
            snapshot_date=snapshot_date,
            cash_balance=cash_balance,
            position_market_value=position_market_value,
            total_equity=total_equity,
            total_return=total_return,
            daily_return=daily_return,
            max_drawdown=max_drawdown,
            position_count=len(positions),
            warnings=warnings,
        )

    def _sum_position_market_value(
        self,
        positions: list[PaperTradingPosition],
    ) -> Decimal:
        total = Decimal("0")

        for position in positions:
            quantity = self._to_decimal(position.quantity)
            if quantity <= 0:
                continue

            total += self._to_decimal(position.market_value)

        return self._quantize_money(total)

    def _calculate_total_return(
        self,
        *,
        initial_cash: Decimal,
        total_equity: Decimal,
    ) -> Decimal:
        if initial_cash <= 0:
            return Decimal("0")

        return self._quantize_return((total_equity - initial_cash) / initial_cash)

    def _calculate_daily_return(
        self,
        *,
        previous_snapshot: PaperTradingEquitySnapshot | None,
        total_equity: Decimal,
    ) -> Decimal | None:
        if previous_snapshot is None:
            return None

        previous_equity = self._to_decimal(previous_snapshot.total_equity)
        if previous_equity <= 0:
            return None

        return self._quantize_return((total_equity - previous_equity) / previous_equity)

    def _calculate_max_drawdown(
        self,
        *,
        historical_snapshots: list[PaperTradingEquitySnapshot],
        snapshot_date: date,
        total_equity: Decimal,
    ) -> Decimal:
        previous_snapshots = [
            snapshot
            for snapshot in historical_snapshots
            if snapshot.snapshot_date != snapshot_date
        ]

        historical_equities = [
            self._to_decimal(snapshot.total_equity)
            for snapshot in previous_snapshots
        ]

        peak_equity = max(
            [total_equity, *historical_equities],
            default=total_equity,
        )

        current_drawdown = Decimal("0")
        if peak_equity > 0 and total_equity < peak_equity:
            current_drawdown = self._quantize_return(
                (peak_equity - total_equity) / peak_equity
            )

        previous_max_drawdown = max(
            [
                self._to_decimal(snapshot.max_drawdown)
                for snapshot in previous_snapshots
                if snapshot.max_drawdown is not None
            ],
            default=Decimal("0"),
        )

        return self._quantize_return(max(current_drawdown, previous_max_drawdown))

    def _find_previous_snapshot(
        self,
        *,
        historical_snapshots: list[PaperTradingEquitySnapshot],
        snapshot_date: date,
    ) -> PaperTradingEquitySnapshot | None:
        previous_snapshots = [
            snapshot
            for snapshot in historical_snapshots
            if snapshot.snapshot_date < snapshot_date
        ]

        if not previous_snapshots:
            return None

        return max(previous_snapshots, key=lambda snapshot: snapshot.snapshot_date)

    def _build_snapshot_response(
        self,
        snapshot: PaperTradingEquitySnapshot,
    ) -> PaperTradingEquitySnapshotResponse:
        return PaperTradingEquitySnapshotResponse.model_validate(snapshot)

    def _today(self) -> date:
        return datetime.now(UTC).date()

    def _to_decimal(
        self,
        value,
    ) -> Decimal:
        return Decimal(str(value))

    def _quantize_money(
        self,
        value: Decimal,
    ) -> Decimal:
        return value.quantize(
            self.MONEY_PRECISION,
            rounding=ROUND_DOWN,
        )

    def _quantize_return(
        self,
        value: Decimal,
    ) -> Decimal:
        return value.quantize(
            self.RETURN_PRECISION,
            rounding=ROUND_DOWN,
        )
