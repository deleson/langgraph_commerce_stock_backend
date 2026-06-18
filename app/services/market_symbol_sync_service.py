"""股票基础信息同步服务。

本服务只处理股票基础信息，不同步 K 线。K 线同步仍由 MarketDataSyncService 负责，
避免出现“全市场全量 K 线同步”这种不可控的外部数据压力。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import BadRequestException
from app.repositories.market_repo import AsyncMarketRepository
from app.schemas.market_data import (
    MarketCode,
    MarketSymbolCreate,
    MarketSymbolSourceCreate,
)
from app.services.market_providers import (
    BaoStockProvider,
    MarketDataProvider,
    MockMarketDataProvider,
    TushareProvider,
)
from app.services.market_symbol_hash_service import MarketSymbolHashService


@dataclass(slots=True)
class MarketSymbolSyncSummary:
    """股票基础信息同步结果摘要。"""

    provider: str
    market: str | None
    fetched_count: int
    source_inserted: int
    source_updated: int
    source_skipped: int
    canonical_inserted: int
    canonical_updated: int
    canonical_skipped: int
    status: str
    error_message: str | None = None


class MarketSymbolSyncService:
    """股票基础信息同步编排器。

    Provider 负责外部调用和字段转换；Repository 负责入库；本服务负责“怎么同步、
    怎么用哈希判断变化、哪个 Provider 能刷新统一表”这些业务规则。
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        provider: MarketDataProvider | None = None,
        provider_name: str | None = None,
        repository: AsyncMarketRepository | None = None,
        hash_service: MarketSymbolHashService | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or AsyncMarketRepository(db)
        self.provider = provider or self._build_provider(provider_name)
        self.hash_service = hash_service or MarketSymbolHashService()

    async def sync_symbol(
        self,
        *,
        symbol: str,
        market: MarketCode,
    ):
        """同步单只股票基础信息，并返回统一表记录。"""

        payload = await self.provider.get_symbol(
            symbol=symbol.strip().upper(),
            market=market,
        )
        await self.persist_provider_symbols([payload])

        saved_symbol = await self.repository.get_symbol(
            symbol=payload.symbol,
            market=payload.market,
        )
        if saved_symbol is None:
            raise BadRequestException(message=f"failed to persist symbol: {market}:{symbol}")
        return saved_symbol

    async def search_symbols(
        self,
        *,
        keyword: str | None = None,
        market: MarketCode | None = None,
        limit: int = 50,
        persist: bool = True,
    ):
        """使用 Provider 搜索并可选入库。

        普通用户名称搜索不应高频调用本方法；MarketService 只会在精确代码缺失或
        占位数据刷新时使用它。后台全量股票池同步请使用 sync_symbol_pool。
        """

        payloads = await self.provider.search_symbols(
            keyword=keyword,
            market=market,
            limit=limit,
        )

        if not persist:
            return [
                self._to_detached_symbol(payload)
                for payload in payloads
            ]

        await self.persist_provider_symbols(payloads)
        return await self.repository.list_symbols_by_keys(
            {(payload.market, payload.symbol) for payload in payloads}
        )

    async def sync_symbol_pool(
        self,
        *,
        market: MarketCode | None = None,
        limit: int | None = None,
    ) -> MarketSymbolSyncSummary:
        """低频同步股票基础信息池。

        Tushare 适合作为低频股票池来源；BaoStock 当前没有被当作全量股票池入口。
        Provider 如果不支持全量同步，会返回 fetched_count=0 的成功结果。
        """

        provider_name = self.provider.provider_name

        try:
            payloads = await self.provider.list_symbols(
                market=market,
                limit=limit,
            )
            persist_summary = await self.persist_provider_symbols(payloads)
            return MarketSymbolSyncSummary(
                provider=provider_name,
                market=market,
                fetched_count=len(payloads),
                source_inserted=persist_summary["source"]["inserted"],
                source_updated=persist_summary["source"]["updated"],
                source_skipped=persist_summary["source"]["skipped"],
                canonical_inserted=persist_summary["canonical"]["inserted"],
                canonical_updated=persist_summary["canonical"]["updated"],
                canonical_skipped=persist_summary["canonical"]["skipped"],
                status="success",
            )
        except Exception as exc:
            return MarketSymbolSyncSummary(
                provider=provider_name,
                market=market,
                fetched_count=0,
                source_inserted=0,
                source_updated=0,
                source_skipped=0,
                canonical_inserted=0,
                canonical_updated=0,
                canonical_skipped=0,
                status="failed",
                error_message=str(exc)[:500],
            )

    async def persist_provider_symbols(
        self,
        payloads: Sequence[MarketSymbolCreate],
    ) -> dict[str, dict[str, int]]:
        """保存 Provider 来源记录，并按优先级刷新统一表。"""

        if not payloads:
            return {
                "source": {"inserted": 0, "updated": 0, "skipped": 0},
                "canonical": {"inserted": 0, "updated": 0, "skipped": 0},
            }

        synced_at = datetime.now(UTC)
        source_payloads: list[MarketSymbolSourceCreate] = []
        canonical_payloads: list[MarketSymbolCreate] = []
        existing_symbols = await self.repository.list_symbols_by_keys(
            {(payload.market, payload.symbol) for payload in payloads}
        )
        existing_symbol_map = {
            (symbol.market, symbol.symbol): symbol
            for symbol in existing_symbols
        }

        for payload in payloads:
            normalized_hash = self.hash_service.normalized_hash(payload)
            raw_payload = payload.raw_payload or self.hash_service.normalized_payload(payload)
            raw_hash = self.hash_service.raw_hash(raw_payload)

            source_payloads.append(
                MarketSymbolSourceCreate(
                    symbol=payload.symbol,
                    market=payload.market,
                    provider=payload.source,
                    provider_symbol=payload.provider_symbol,
                    name=payload.name,
                    currency=payload.currency,
                    exchange=payload.exchange,
                    list_status=payload.list_status,
                    is_active=payload.is_active,
                    raw_payload=raw_payload,
                    raw_hash=raw_hash,
                    normalized_hash=normalized_hash,
                    sync_status="success",
                    last_synced_at=synced_at,
                    last_sync_error=None,
                )
            )

            existing_symbol = existing_symbol_map.get((payload.market, payload.symbol))
            if self._can_refresh_canonical(payload, existing_symbol):
                canonical_payloads.append(
                    MarketSymbolCreate(
                        symbol=payload.symbol,
                        market=payload.market,
                        name=payload.name,
                        currency=payload.currency,
                        exchange=payload.exchange,
                        provider_symbol=payload.provider_symbol,
                        list_status=payload.list_status,
                        source=payload.source,
                        is_active=payload.is_active,
                        data_hash=normalized_hash,
                        last_synced_at=synced_at,
                        sync_status="success",
                        last_sync_error=None,
                    )
                )

        source_summary = await self.repository.upsert_symbol_sources_bulk(source_payloads)
        canonical_summary = await self.repository.upsert_symbols_bulk(canonical_payloads)

        return {
            "source": source_summary,
            "canonical": canonical_summary,
        }

    def _can_refresh_canonical(
        self,
        payload: MarketSymbolCreate,
        existing,
    ) -> bool:
        if existing is None:
            return True

        existing_priority = self._provider_priority(existing.source)
        incoming_priority = self._provider_priority(payload.source)

        if payload.source == existing.source:
            return True

        if existing.source == "mock" and payload.source != "mock":
            return True

        # 数字越小优先级越高。BaoStock 可补齐缺失数据，但不能无脑覆盖 Tushare。
        return incoming_priority <= existing_priority

    def _provider_priority(
        self,
        provider_name: str | None,
    ) -> int:
        settings = get_settings()
        configured_names = [
            settings.market_symbol_primary_provider,
            *settings.market_symbol_fallback_providers.split(","),
        ]
        normalized_names = [
            name.strip().lower()
            for name in configured_names
            if name and name.strip()
        ]

        try:
            return normalized_names.index((provider_name or "").strip().lower())
        except ValueError:
            return len(normalized_names) + 1

    def _build_provider(
        self,
        provider_name: str | None = None,
    ) -> MarketDataProvider:
        settings = get_settings()
        resolved_provider = (
            provider_name
            or settings.market_symbol_sync_provider
            or settings.market_data_primary_provider
        ).strip().lower()

        if resolved_provider == "mock":
            return MockMarketDataProvider()

        if resolved_provider == "baostock":
            if not settings.baostock_enabled:
                raise BadRequestException(message="baostock provider is disabled")
            return BaoStockProvider()

        if resolved_provider == "tushare":
            if not settings.tushare_enabled:
                raise BadRequestException(message="tushare provider is disabled")
            return TushareProvider()

        raise BadRequestException(message=f"unsupported market symbol provider: {resolved_provider}")

    def _to_detached_symbol(
        self,
        payload: MarketSymbolCreate,
    ):
        from app.models.market_symbol import MarketSymbol

        return MarketSymbol(
            symbol=payload.symbol,
            market=payload.market,
            name=payload.name,
            currency=payload.currency,
            exchange=payload.exchange,
            provider_symbol=payload.provider_symbol,
            list_status=payload.list_status,
            source=payload.source,
            is_active=payload.is_active,
        )
