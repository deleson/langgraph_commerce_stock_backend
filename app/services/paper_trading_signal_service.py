from __future__ import annotations

"""纸面交易信号读取服务。

本文件负责把当前用户自选股转换成纸面交易 tick 的扫描对象，
并读取 Market Overview、数据质量和策略信号。

它只判断哪些股票具备生成模拟订单的条件，不创建订单、不更新持仓、
不更新账户现金，也不生成权益快照。
"""

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.market import MarketOverviewResponse
from app.schemas.paper_trading import (
    PaperTradingTickRequest,
    PaperTradingUnavailableReason,
)
from app.services.market_service import MarketService
from app.services.watchlist_service import AsyncWatchlistService


@dataclass(slots=True)
class PaperTradingUniverseItem:
    """纸面交易 tick 扫描股票池中的单只股票。"""

    symbol: str
    market: str
    name: str | None = None
    notes: str | None = None


@dataclass(slots=True)
class PaperTradingSignalItem:
    """单只股票的纸面交易信号上下文。"""

    symbol: str
    market: str
    name: str | None = None
    notes: str | None = None
    overview: MarketOverviewResponse | None = None
    can_generate_order: bool = False
    action: str | None = None
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def quote(self):
        return self.overview.quote if self.overview else None

    @property
    def data_quality(self):
        return self.overview.data_quality if self.overview else None

    @property
    def strategy_signal(self):
        return self.overview.strategy_signal if self.overview else None


@dataclass(slots=True)
class PaperTradingSignalContext:
    """一次纸面交易 tick 的信号读取结果。"""

    user_id: int
    request: PaperTradingTickRequest
    universe_items: list[PaperTradingUniverseItem]
    items: list[PaperTradingSignalItem]
    actionable_items: list[PaperTradingSignalItem]
    unavailable_reason: PaperTradingUnavailableReason | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class PaperTradingSignalService:
    """收集纸面交易 tick 所需的确定性信号输入。

    这个 Service 只读取自选股、行情概览、数据质量和策略信号。
    buy / sell 信号会进入 actionable_items；hold / observe 只记录原因，不生成订单。
    """

    TIMEFRAME = "1d"
    MARKET_OVERVIEW_LIMIT = 120
    TECHNICAL_INDICATOR_LIMIT = 120
    STRATEGY_SIGNAL_LIMIT = 120
    DATA_QUALITY_MIN_REQUIRED = 35
    DATA_QUALITY_STALE_AFTER_DAYS = 7
    ACTIONABLE_SIGNALS = {"buy", "sell"}

    def __init__(
        self,
        db: AsyncSession,
        *,
        watchlist_service: AsyncWatchlistService | None = None,
        market_service: MarketService | None = None,
    ) -> None:
        self.db = db
        self.watchlist_service = watchlist_service or AsyncWatchlistService(db)
        self.market_service = market_service or MarketService(db)

    async def collect_signal_context(
        self,
        *,
        user: User,
        request: PaperTradingTickRequest,
    ) -> PaperTradingSignalContext:
        """收集一次 tick 的所有股票信号。

        数据质量为空、不足、过旧或有错误时，不允许生成模拟订单。
        这样可以避免纸面交易在不可靠行情上推进。
        """

        warnings: list[str] = []
        errors: list[str] = []

        universe_items = await self._build_universe_items(
            user=user,
            request=request,
            warnings=warnings,
        )

        if not universe_items:
            return PaperTradingSignalContext(
                user_id=user.id,
                request=request,
                universe_items=[],
                items=[],
                actionable_items=[],
                unavailable_reason=PaperTradingUnavailableReason.NO_WATCHLIST,
                warnings=warnings or ["当前用户自选股为空，无法推进纸面交易。"],
                errors=errors,
            )

        items: list[PaperTradingSignalItem] = []
        for universe_item in universe_items:
            item = await self._collect_one_item(universe_item)
            items.append(item)
            warnings.extend(item.warnings)
            errors.extend(item.errors)

        actionable_items = [
            item for item in items if item.can_generate_order
        ]

        unavailable_reason = None
        if not any(item.overview for item in items):
            unavailable_reason = PaperTradingUnavailableReason.NO_DATA
            warnings.append("本次纸面交易 tick 没有读取到可用行情数据。")

        return PaperTradingSignalContext(
            user_id=user.id,
            request=request,
            universe_items=universe_items,
            items=items,
            actionable_items=actionable_items,
            unavailable_reason=unavailable_reason,
            warnings=self._deduplicate_messages(warnings),
            errors=self._deduplicate_messages(errors),
        )

    async def _build_universe_items(
        self,
        *,
        user: User,
        request: PaperTradingTickRequest,
        warnings: list[str],
    ) -> list[PaperTradingUniverseItem]:
        watchlist_items = await self.watchlist_service.list_my_watchlist(user)

        if not watchlist_items:
            warnings.append("当前用户自选股为空，无法执行纸面交易 tick。")
            return []

        limited_items = watchlist_items[: request.max_symbols]

        if len(watchlist_items) > len(limited_items):
            warnings.append(
                f"本次纸面交易 tick 最多处理 {request.max_symbols} 只自选股，"
                f"已跳过 {len(watchlist_items) - len(limited_items)} 只。"
            )

        return [
            PaperTradingUniverseItem(
                symbol=self._normalize_text(item.symbol),
                market=self._normalize_text(item.market),
                name=item.name,
                notes=item.notes,
            )
            for item in limited_items
        ]

    async def _collect_one_item(
        self,
        item: PaperTradingUniverseItem,
    ) -> PaperTradingSignalItem:
        warnings: list[str] = []
        errors: list[str] = []

        try:
            overview = await self.market_service.get_overview(
                symbol=item.symbol,
                market=item.market,
                timeframe=self.TIMEFRAME,
                limit=self.MARKET_OVERVIEW_LIMIT,
                include_technical_indicators=True,
                technical_indicator_limit=self.TECHNICAL_INDICATOR_LIMIT,
                include_data_quality=True,
                data_quality_min_required=self.DATA_QUALITY_MIN_REQUIRED,
                data_quality_stale_after_days=self.DATA_QUALITY_STALE_AFTER_DAYS,
                include_strategy_signal=True,
                strategy_signal_limit=self.STRATEGY_SIGNAL_LIMIT,
                strategy_signal_include_detail=True,
                strategy_signal_min_required=self.DATA_QUALITY_MIN_REQUIRED,
                strategy_signal_stale_after_days=self.DATA_QUALITY_STALE_AFTER_DAYS,
            )
        except Exception as exc:
            errors.append(
                f"{item.market}:{item.symbol} 纸面交易信号读取失败："
                f"{self._safe_error_message(exc)}"
            )
            return PaperTradingSignalItem(
                symbol=item.symbol,
                market=item.market,
                name=item.name,
                notes=item.notes,
                overview=None,
                can_generate_order=False,
                action=None,
                reason="行情或策略信号读取失败",
                warnings=warnings,
                errors=errors,
            )

        warnings.extend(self._collect_quality_warnings(overview))
        errors.extend(self._collect_quality_errors(overview))

        can_generate_order, action, reason = self._evaluate_actionable_signal(overview)

        return PaperTradingSignalItem(
            symbol=item.symbol,
            market=item.market,
            name=item.name,
            notes=item.notes,
            overview=overview,
            can_generate_order=can_generate_order,
            action=action,
            reason=reason,
            warnings=self._deduplicate_messages(warnings),
            errors=self._deduplicate_messages(errors),
        )

    def _evaluate_actionable_signal(
        self,
        overview: MarketOverviewResponse,
    ) -> tuple[bool, str | None, str]:
        """判断单只股票是否可以生成模拟订单。

        只有数据质量通过，且策略信号为 buy / sell 时才返回 can_generate_order=True。
        这一步仍然只是规则信号，不代表真实交易建议。
        """

        data_quality = overview.data_quality
        if data_quality is None:
            return False, None, "缺少数据质量报告，暂不生成模拟订单"

        if data_quality.errors:
            return False, None, "数据质量存在错误，暂不生成模拟订单"

        if data_quality.is_empty:
            return False, None, "K 线数据为空，暂不生成模拟订单"

        if not data_quality.is_enough:
            return False, None, "K 线数量不足，暂不生成模拟订单"

        if data_quality.is_stale:
            return False, None, "行情数据过旧，暂不生成模拟订单"

        strategy_signal = overview.strategy_signal
        if strategy_signal is None:
            return False, None, "缺少策略信号，暂不生成模拟订单"

        if strategy_signal.status != "available":
            return False, None, "策略信号不可用，暂不生成模拟订单"

        if strategy_signal.signal not in self.ACTIONABLE_SIGNALS:
            return (
                False,
                strategy_signal.signal,
                f"当前策略信号为 {strategy_signal.signal}，不生成模拟订单",
            )

        return (
            True,
            strategy_signal.signal,
            strategy_signal.summary,
        )

    def _collect_quality_warnings(
        self,
        overview: MarketOverviewResponse,
    ) -> list[str]:
        if overview.data_quality is None:
            return []

        return list(overview.data_quality.warnings or [])

    def _collect_quality_errors(
        self,
        overview: MarketOverviewResponse,
    ) -> list[str]:
        if overview.data_quality is None:
            return []

        return list(overview.data_quality.errors or [])

    def _normalize_text(
        self,
        value: str | None,
    ) -> str:
        return (value or "").strip().upper()

    def _deduplicate_messages(
        self,
        messages: list[str],
    ) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []

        for message in messages:
            normalized = message.strip()
            if not normalized or normalized in seen:
                continue

            seen.add(normalized)
            result.append(normalized)

        return result

    def _safe_error_message(
        self,
        exc: Exception,
    ) -> str:
        message = str(exc).strip()
        if not message:
            return exc.__class__.__name__

        return message[:300]
