from __future__ import annotations

"""量化提醒扫描数据收集服务。

本文件负责为一次提醒扫描准备市场数据上下文：
从当前用户自选股构建扫描股票池，再读取 Market Overview、数据质量、技术指标和策略信号。

它只负责“拿数据”，不判断规则是否触发，也不写提醒事件。
"""

from dataclasses import dataclass, field

from app.models.user import User
from app.schemas.market import MarketOverviewResponse
from app.schemas.quant_alert import QuantAlertScanRequest, QuantAlertUnavailableReason
from app.services.market_service import MarketService
from app.services.watchlist_service import AsyncWatchlistService


@dataclass(slots=True)
class QuantAlertUniverseItem:
    """量化提醒扫描股票池中的单只股票。"""

    symbol: str
    market: str
    name: str | None = None
    notes: str | None = None
    alert_enabled: bool = True


@dataclass(slots=True)
class QuantAlertDataItem:
    """单只股票在扫描时使用的行情与策略上下文。"""

    symbol: str
    market: str
    name: str | None = None
    notes: str | None = None
    alert_enabled: bool = True
    overview: MarketOverviewResponse | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def quote(self):
        return self.overview.quote if self.overview else None

    @property
    def technical_indicators(self):
        return self.overview.technical_indicators if self.overview else None

    @property
    def data_quality(self):
        return self.overview.data_quality if self.overview else None

    @property
    def strategy_signal(self):
        return self.overview.strategy_signal if self.overview else None


@dataclass(slots=True)
class QuantAlertDataContext:
    """一次量化提醒扫描的数据上下文。"""

    user_id: int
    request: QuantAlertScanRequest
    universe_items: list[QuantAlertUniverseItem]
    items: list[QuantAlertDataItem]
    unavailable_reason: QuantAlertUnavailableReason | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class QuantAlertDataService:
    """收集量化提醒扫描所需的确定性行情数据。

    这个 Service 只读取和聚合数据，不判断是否触发提醒，
    不创建 QuantAlertEvent，也不创建 Notification。
    """

    TECHNICAL_INDICATOR_LIMIT = 120
    STRATEGY_SIGNAL_LIMIT = 120
    DATA_QUALITY_MIN_REQUIRED = 35
    DATA_QUALITY_STALE_AFTER_DAYS = 7

    def __init__(
        self,
        watchlist_service: AsyncWatchlistService,
        market_service: MarketService,
    ) -> None:
        self.watchlist_service = watchlist_service
        self.market_service = market_service

    async def collect_data_for_scan(
        self,
        user: User,
        request: QuantAlertScanRequest,
    ) -> QuantAlertDataContext:
        """收集一次扫描所需的数据。

        如果用户没有自选股、没有开启提醒，或外部行情不可用，
        会通过 unavailable_reason / warnings 返回，而不是直接抛出业务异常。
        """

        warnings: list[str] = []
        errors: list[str] = []

        universe_items = await self._build_universe_items(user, request, warnings)

        if not universe_items:
            return QuantAlertDataContext(
                user_id=user.id,
                request=request,
                universe_items=[],
                items=[],
                unavailable_reason=QuantAlertUnavailableReason.EMPTY_WATCHLIST,
                warnings=warnings
                or ["当前没有可扫描的自选股，可能是自选股为空或提醒开关未开启。"],
                errors=errors,
            )

        items: list[QuantAlertDataItem] = []
        for universe_item in universe_items:
            item = await self._get_one_item_data(universe_item)
            items.append(item)
            warnings.extend(item.warnings)
            errors.extend(item.errors)

        unavailable_reason = None
        if not any(item.overview for item in items):
            unavailable_reason = QuantAlertUnavailableReason.NO_DATA
            warnings.append("本次扫描没有读取到可用于提醒判断的行情数据。")

        return QuantAlertDataContext(
            user_id=user.id,
            request=request,
            universe_items=universe_items,
            items=items,
            unavailable_reason=unavailable_reason,
            warnings=self._deduplicate_messages(warnings),
            errors=self._deduplicate_messages(errors),
        )

    async def _build_universe_items(
        self,
        user: User,
        request: QuantAlertScanRequest,
        warnings: list[str],
    ) -> list[QuantAlertUniverseItem]:
        """从当前用户自选股构建提醒扫描股票池。

        这里必须使用当前用户的自选股，不能扫描其他用户的股票池。
        request.symbols / request.market 只是进一步过滤，不改变用户隔离边界。
        """

        watchlist_items = await self.watchlist_service.list_my_watchlist(user)

        if not watchlist_items:
            warnings.append("当前用户自选股为空，无法执行量化提醒扫描。")
            return []

        enabled_items = [item for item in watchlist_items if item.alert_enabled]
        if not enabled_items:
            warnings.append("当前用户自选股均未开启提醒，无法执行量化提醒扫描。")
            return []

        market = self._normalize_optional_text(request.market)
        if market:
            enabled_items = [
                item for item in enabled_items if self._normalize_text(item.market) == market
            ]

        request_symbols = self._build_request_symbol_set(request)
        if request_symbols:
            enabled_items = [
                item
                for item in enabled_items
                if (
                    self._normalize_text(item.market),
                    self._normalize_text(item.symbol),
                )
                in request_symbols
                or ("*", self._normalize_text(item.symbol)) in request_symbols
            ]

        limited_items = enabled_items[: request.max_watchlist_items]

        if len(enabled_items) > len(limited_items):
            warnings.append(
                f"本次扫描最多处理 {request.max_watchlist_items} 只自选股，"
                f"已跳过 {len(enabled_items) - len(limited_items)} 只。"
            )

        return [
            QuantAlertUniverseItem(
                symbol=self._normalize_text(item.symbol),
                market=self._normalize_text(item.market),
                name=item.name,
                notes=item.notes,
                alert_enabled=item.alert_enabled,
            )
            for item in limited_items
        ]

    async def _get_one_item_data(
        self,
        item: QuantAlertUniverseItem,
    ) -> QuantAlertDataItem:
        warnings: list[str] = []
        errors: list[str] = []

        try:
            overview = await self.market_service.get_overview(
                symbol=item.symbol,
                market=item.market,
                timeframe="1d",
                limit=self.TECHNICAL_INDICATOR_LIMIT,
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
                f"{item.market}:{item.symbol} 提醒数据读取失败："
                f"{self._safe_error_message(exc)}"
            )
            return QuantAlertDataItem(
                symbol=item.symbol,
                market=item.market,
                name=item.name,
                notes=item.notes,
                alert_enabled=item.alert_enabled,
                overview=None,
                warnings=warnings,
                errors=errors,
            )

        if overview.data_quality:
            warnings.extend(overview.data_quality.warnings or [])
            errors.extend(overview.data_quality.errors or [])

        return QuantAlertDataItem(
            symbol=item.symbol,
            market=item.market,
            name=item.name,
            notes=item.notes,
            alert_enabled=item.alert_enabled,
            overview=overview,
            warnings=self._deduplicate_messages(warnings),
            errors=self._deduplicate_messages(errors),
        )

    def _build_request_symbol_set(
        self,
        request: QuantAlertScanRequest,
    ) -> set[tuple[str, str]]:
        symbols = request.symbols or []
        market = self._normalize_optional_text(request.market)

        if market:
            return {
                (market, self._normalize_text(symbol))
                for symbol in symbols
            }

        return {
            ("*", self._normalize_text(symbol))
            for symbol in symbols
        }

    def _normalize_optional_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = self._normalize_text(value)
        return normalized or None

    def _normalize_text(self, value: str | None) -> str:
        return (value or "").strip().upper()

    def _deduplicate_messages(self, messages: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for message in messages:
            normalized = message.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    def _safe_error_message(self, exc: Exception) -> str:
        message = str(exc).strip()
        if not message:
            return exc.__class__.__name__
        return message[:300]
