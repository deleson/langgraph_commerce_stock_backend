from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.market_repo import AsyncMarketRepository
from app.schemas.market_data import (
    MarketCandleQuery,
    MarketCode,
    MarketProviderCandle,
    MarketSymbolCreate,
)
from app.services.market_data_sync_service import MarketDataSyncService
from app.services.market_providers.base import MarketDataProvider
from app.services.market_service import MarketService
from app.services.market_symbol_hash_service import MarketSymbolHashService
from app.services.market_symbol_sync_service import MarketSymbolSyncService


class FakeSymbolProvider(MarketDataProvider):
    def __init__(
        self,
        *,
        provider_name: str = "tushare",
        name: str = "贵州茅台",
        fail_list: bool = False,
    ) -> None:
        self.provider_name = provider_name
        self.name = name
        self.fail_list = fail_list
        self.search_calls = 0
        self.get_calls = 0
        self.list_calls = 0

    @property
    def supported_markets(self) -> set[MarketCode]:
        return {"CN"}

    @property
    def supported_timeframes(self) -> set[str]:
        return {"1d"}

    async def search_symbols(
        self,
        *,
        keyword: str | None = None,
        market: MarketCode | None = None,
        limit: int = 50,
    ) -> list[MarketSymbolCreate]:
        self.search_calls += 1
        if keyword != "600519":
            return []
        return [self._symbol("600519")]

    async def list_symbols(
        self,
        *,
        market: MarketCode | None = None,
        limit: int | None = None,
    ) -> list[MarketSymbolCreate]:
        self.list_calls += 1
        if self.fail_list:
            raise RuntimeError("provider quota exceeded")
        symbols = [
            self._symbol("600519"),
            self._symbol("002594", name="比亚迪"),
        ]
        return symbols[:limit] if limit is not None else symbols

    async def get_symbol(
        self,
        *,
        symbol: str,
        market: MarketCode,
    ) -> MarketSymbolCreate:
        self.get_calls += 1
        return self._symbol(symbol)

    async def get_candles(
        self,
        query: MarketCandleQuery,
    ) -> list[MarketProviderCandle]:
        return [
            MarketProviderCandle(
                symbol=query.symbol,
                market=query.market,
                candle_time=datetime.now(UTC),
                open_price=Decimal("1"),
                high_price=Decimal("1"),
                low_price=Decimal("1"),
                close_price=Decimal("1"),
                volume=1,
                source=self.provider_name,
            )
        ]

    def _symbol(
        self,
        symbol: str,
        *,
        name: str | None = None,
    ) -> MarketSymbolCreate:
        suffix = "SH" if symbol.startswith("6") else "SZ"
        return MarketSymbolCreate(
            symbol=symbol,
            market="CN",
            name=name or self.name,
            currency="CNY",
            exchange="SSE" if suffix == "SH" else "SZSE",
            provider_symbol=f"{symbol}.{suffix}" if self.provider_name == "tushare" else f"{suffix.lower()}.{symbol}",
            list_status="L",
            source=self.provider_name,
            is_active=True,
            raw_payload={
                "symbol": symbol,
                "name": name or self.name,
                "provider": self.provider_name,
            },
        )


def test_market_symbol_hash_ignores_runtime_fields() -> None:
    service = MarketSymbolHashService()
    first = MarketSymbolCreate(
        symbol="600519",
        market="CN",
        name="贵州茅台",
        currency="CNY",
        exchange="SSE",
        provider_symbol="600519.SH",
        list_status="L",
        source="tushare",
        is_active=True,
        last_synced_at=datetime.now(UTC),
        sync_status="success",
    )
    second = first.model_copy(
        update={
            "last_synced_at": datetime.now(UTC),
            "sync_status": "failed",
            "last_sync_error": "quota exceeded",
        }
    )

    assert service.normalized_hash(first) == service.normalized_hash(second)


async def test_symbol_pool_sync_is_idempotent_with_hash(
    db_session: AsyncSession,
) -> None:
    provider = FakeSymbolProvider(provider_name="tushare")
    service = MarketSymbolSyncService(db_session, provider=provider)

    first = await service.sync_symbol_pool(market="CN")
    second = await service.sync_symbol_pool(market="CN")

    assert first.status == "success"
    assert first.fetched_count == 2
    assert first.source_inserted == 2
    assert first.canonical_inserted == 2
    assert second.source_skipped == 2
    assert second.canonical_skipped == 2


async def test_provider_sources_are_separated_and_priority_preserves_tushare(
    db_session: AsyncSession,
) -> None:
    repository = AsyncMarketRepository(db_session)
    tushare_service = MarketSymbolSyncService(
        db_session,
        provider=FakeSymbolProvider(provider_name="tushare", name="贵州茅台"),
        repository=repository,
    )
    baostock_service = MarketSymbolSyncService(
        db_session,
        provider=FakeSymbolProvider(provider_name="baostock", name="茅台A"),
        repository=repository,
    )

    await tushare_service.sync_symbol_pool(market="CN", limit=1)
    await baostock_service.sync_symbol_pool(market="CN", limit=1)

    canonical = await repository.get_symbol(symbol="600519", market="CN")
    tushare_source = await repository.get_symbol_source(
        provider="tushare",
        market="CN",
        symbol="600519",
    )
    baostock_source = await repository.get_symbol_source(
        provider="baostock",
        market="CN",
        symbol="600519",
    )

    assert canonical is not None
    assert canonical.name == "贵州茅台"
    assert canonical.source == "tushare"
    assert tushare_source is not None
    assert baostock_source is not None
    assert baostock_source.name == "茅台A"


async def test_name_search_does_not_call_provider(
    db_session: AsyncSession,
) -> None:
    provider = FakeSymbolProvider(provider_name="tushare")
    sync_service = MarketDataSyncService(db_session, provider=provider)
    service = MarketService(db_session, sync_service=sync_service)

    result = await service.search_stocks(keyword="贵州茅台", market="CN")

    assert result == []
    assert provider.search_calls == 0


async def test_exact_code_search_can_use_provider_fallback(
    db_session: AsyncSession,
) -> None:
    provider = FakeSymbolProvider(provider_name="baostock", name="贵州茅台")
    sync_service = MarketDataSyncService(db_session, provider=provider)
    service = MarketService(db_session, sync_service=sync_service)

    result = await service.search_stocks(keyword="600519", market="CN")

    assert len(result) == 1
    assert result[0].symbol == "600519"
    assert result[0].name == "贵州茅台"
    assert result[0].source == "baostock"
    assert provider.search_calls == 1


async def test_sync_symbol_uses_provider_get_symbol(
    db_session: AsyncSession,
) -> None:
    provider = FakeSymbolProvider(provider_name="baostock", name="贵州茅台")
    service = MarketSymbolSyncService(db_session, provider=provider)

    result = await service.sync_symbol(symbol="600519", market="CN")

    assert result.symbol == "600519"
    assert result.name == "贵州茅台"
    assert result.source == "baostock"
    assert provider.get_calls == 1
    assert provider.search_calls == 0


async def test_symbol_pool_sync_returns_failed_summary_on_provider_error(
    db_session: AsyncSession,
) -> None:
    service = MarketSymbolSyncService(
        db_session,
        provider=FakeSymbolProvider(provider_name="tushare", fail_list=True),
    )

    result = await service.sync_symbol_pool(market="CN")

    assert result.status == "failed"
    assert result.fetched_count == 0
    assert "quota exceeded" in (result.error_message or "")
