"""自选股日 K 批量同步服务。

本服务只同步用户已经关注过的股票，不做全市场 K 线同步。它用于 Celery Beat
低频维护 K 线数据，让股票详情、技术指标、日报和提醒扫描优先读取数据库，减少
用户请求链路里的 Provider 调用。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_candle import MarketCandle
from app.repositories.market_repo import AsyncMarketRepository
from app.repositories.watchlist_repo import AsyncWatchlistRepository
from app.schemas.market_data import AdjustType, CandleTimeframe, MarketCandleQuery, MarketCode
from app.services.market_data_sync_service import MarketDataSyncService


@dataclass(slots=True)
class WatchlistCandleSyncSymbolResult:
    """单只自选股 K 线同步结果摘要。"""

    symbol: str
    market: str
    status: str
    provider: str | None = None
    saved_count: int = 0
    skipped_reason: str | None = None
    error_message: str | None = None
    first_candle_time: str | None = None
    last_candle_time: str | None = None


@dataclass(slots=True)
class WatchlistCandleSyncSummary:
    """自选股批量同步任务汇总结果。"""

    status: str
    market: str
    timeframe: str
    adjust_type: str
    source: str
    fallback_sources: list[str]
    requested_symbol_count: int = 0
    stale_symbol_count: int = 0
    skipped_symbol_count: int = 0
    synced_symbol_count: int = 0
    failed_symbol_count: int = 0
    total_saved_candles: int = 0
    provider_success_counts: dict[str, int] = field(default_factory=dict)
    provider_failure_counts: dict[str, int] = field(default_factory=dict)
    results: list[WatchlistCandleSyncSymbolResult] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    def to_result(self) -> dict[str, object]:
        return {
            "status": self.status,
            "market": self.market,
            "timeframe": self.timeframe,
            "adjust_type": self.adjust_type,
            "source": self.source,
            "fallback_sources": self.fallback_sources,
            "requested_symbol_count": self.requested_symbol_count,
            "stale_symbol_count": self.stale_symbol_count,
            "skipped_symbol_count": self.skipped_symbol_count,
            "synced_symbol_count": self.synced_symbol_count,
            "failed_symbol_count": self.failed_symbol_count,
            "total_saved_candles": self.total_saved_candles,
            "provider_success_counts": self.provider_success_counts,
            "provider_failure_counts": self.provider_failure_counts,
            "results": [asdict(result) for result in self.results[:50]],
            "errors": self.errors[:20],
        }


class WatchlistCandleSyncService:
    """批量同步自选股日 K 的业务编排器。"""

    def __init__(
        self,
        db: AsyncSession,
        *,
        watchlist_repository: AsyncWatchlistRepository | None = None,
        market_repository: AsyncMarketRepository | None = None,
        sync_service_factory: Callable[[str], MarketDataSyncService] | None = None,
    ) -> None:
        self.db = db
        self.watchlist_repository = watchlist_repository or AsyncWatchlistRepository(db)
        self.market_repository = market_repository or AsyncMarketRepository(db)
        self.sync_service_factory = sync_service_factory or (
            lambda provider_name: MarketDataSyncService(db, provider_name=provider_name)
        )

    async def sync_watchlist_candles(
        self,
        *,
        market: MarketCode = "CN",
        timeframe: CandleTimeframe = "1d",
        limit: int = 120,
        adjust_type: AdjustType = "none",
        source: str = "baostock",
        fallback_sources: list[str] | None = None,
        max_symbols: int = 300,
        batch_size: int = 50,
        stale_after_days: int = 3,
    ) -> WatchlistCandleSyncSummary:
        providers = self._normalize_providers(source, fallback_sources or [])
        primary_source = providers[0]
        fallback_provider_names = providers[1:]

        summary = WatchlistCandleSyncSummary(
            status="success",
            market=market,
            timeframe=timeframe,
            adjust_type=adjust_type,
            source=primary_source,
            fallback_sources=fallback_provider_names,
        )

        symbol_pairs = await self.watchlist_repository.list_distinct_symbols(
            market=market,
            limit=max_symbols,
        )
        summary.requested_symbol_count = len(symbol_pairs)

        if not symbol_pairs:
            return summary

        effective_batch_size = max(batch_size, 1)
        for start in range(0, len(symbol_pairs), effective_batch_size):
            batch = symbol_pairs[start : start + effective_batch_size]
            for item_market, item_symbol in batch:
                await self._sync_one_symbol_if_needed(
                    summary=summary,
                    symbol=item_symbol,
                    market=item_market,
                    timeframe=timeframe,
                    limit=limit,
                    adjust_type=adjust_type,
                    providers=providers,
                    stale_after_days=stale_after_days,
                )

        if summary.failed_symbol_count and summary.synced_symbol_count == 0:
            summary.status = "failed" if summary.skipped_symbol_count == 0 else "partial_success"
        elif summary.failed_symbol_count:
            summary.status = "partial_success"
        else:
            summary.status = "success"

        return summary

    async def _sync_one_symbol_if_needed(
        self,
        *,
        summary: WatchlistCandleSyncSummary,
        symbol: str,
        market: str,
        timeframe: str,
        limit: int,
        adjust_type: str,
        providers: list[str],
        stale_after_days: int,
    ) -> None:
        normalized_symbol = symbol.strip().upper()
        latest = await self._get_latest_candle(
            symbol=normalized_symbol,
            market=market,
            timeframe=timeframe,
            adjust_type=adjust_type,
        )

        if latest is not None and not self._is_stale(latest, stale_after_days):
            summary.skipped_symbol_count += 1
            summary.results.append(
                WatchlistCandleSyncSymbolResult(
                    symbol=normalized_symbol,
                    market=market,
                    status="skipped",
                    provider=latest.source,
                    skipped_reason="fresh_candles_exist",
                    last_candle_time=latest.candle_time.isoformat(),
                )
            )
            return

        summary.stale_symbol_count += 1
        sync_result = await self._sync_with_providers(
            symbol=normalized_symbol,
            market=market,
            timeframe=timeframe,
            limit=limit,
            adjust_type=adjust_type,
            providers=providers,
        )

        summary.results.append(sync_result)
        if sync_result.status == "success":
            summary.synced_symbol_count += 1
            summary.total_saved_candles += sync_result.saved_count
            if sync_result.provider:
                summary.provider_success_counts[sync_result.provider] = (
                    summary.provider_success_counts.get(sync_result.provider, 0) + 1
                )
            return

        summary.failed_symbol_count += 1
        if sync_result.provider:
            summary.provider_failure_counts[sync_result.provider] = (
                summary.provider_failure_counts.get(sync_result.provider, 0) + 1
            )
        summary.errors.append(
            {
                "symbol": normalized_symbol,
                "market": market,
                "provider": sync_result.provider or "unknown",
                "reason": sync_result.error_message or "sync failed",
            }
        )

    async def _sync_with_providers(
        self,
        *,
        symbol: str,
        market: str,
        timeframe: str,
        limit: int,
        adjust_type: str,
        providers: list[str],
    ) -> WatchlistCandleSyncSymbolResult:
        errors: list[str] = []
        last_provider: str | None = None

        for provider_name in providers:
            last_provider = provider_name
            try:
                sync_service = self.sync_service_factory(provider_name)
                candles = await sync_service.sync_candles(
                    symbol=symbol,
                    market=market,  # type: ignore[arg-type]
                    timeframe=timeframe,  # type: ignore[arg-type]
                    limit=limit,
                    adjust_type=adjust_type,  # type: ignore[arg-type]
                )
                return WatchlistCandleSyncSymbolResult(
                    symbol=symbol,
                    market=market,
                    status="success",
                    provider=provider_name,
                    saved_count=len(candles),
                    first_candle_time=candles[0].candle_time.isoformat() if candles else None,
                    last_candle_time=candles[-1].candle_time.isoformat() if candles else None,
                )
            except Exception as exc:
                errors.append(f"{provider_name}: {self._safe_error_message(exc)}")
                continue

        return WatchlistCandleSyncSymbolResult(
            symbol=symbol,
            market=market,
            status="failed",
            provider=last_provider,
            error_message="; ".join(errors)[:500],
        )

    async def _get_latest_candle(
        self,
        *,
        symbol: str,
        market: str,
        timeframe: str,
        adjust_type: str,
    ) -> MarketCandle | None:
        candles = await self.market_repository.list_candles(
            MarketCandleQuery(
                symbol=symbol,
                market=market,  # type: ignore[arg-type]
                timeframe=timeframe,  # type: ignore[arg-type]
                limit=1,
                adjust_type=adjust_type,  # type: ignore[arg-type]
                source=None,
            )
        )
        return candles[-1] if candles else None

    def _is_stale(
        self,
        candle: MarketCandle,
        stale_after_days: int,
    ) -> bool:
        latest_date = candle.candle_time.astimezone(UTC).date()
        current_date = datetime.now(UTC).date()
        return (current_date - latest_date).days > stale_after_days

    def _normalize_providers(
        self,
        source: str,
        fallback_sources: list[str],
    ) -> list[str]:
        providers: list[str] = []
        for provider_name in [source, *fallback_sources]:
            normalized = provider_name.strip().lower()
            if normalized and normalized not in providers:
                providers.append(normalized)

        return providers or ["mock"]

    def _safe_error_message(
        self,
        exc: Exception,
    ) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        return message[:300]
