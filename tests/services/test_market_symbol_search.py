from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

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
from app.services.market_providers.tushare import TushareProvider
from app.services.market_service import MarketService


class FakeDataFrame:
    def __init__(self, records: list[dict[str, str]]) -> None:
        self.records = records
        self.empty = not records

    def to_dict(self, orient: str) -> list[dict[str, str]]:
        assert orient == "records"
        return self.records


class FakeTusharePro:
    def __init__(self) -> None:
        self.stock_basic_calls: list[dict[str, str]] = []

    def stock_basic(self, **kwargs) -> FakeDataFrame:
        self.stock_basic_calls.append(kwargs)
        return FakeDataFrame(
            [
                {
                    "ts_code": "600519.SH",
                    "symbol": "600519",
                    "name": "贵州茅台",
                    "exchange": "SSE",
                    "curr_type": "CNY",
                    "list_status": "L",
                }
            ]
        )


class FakeSecret:
    def get_secret_value(self) -> str:
        return "fake-token"


class FakeProvider(MarketDataProvider):
    provider_name = "tushare"

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
        assert keyword == "600519"
        assert market == "CN"
        return [
            MarketSymbolCreate(
                symbol="600519",
                market="CN",
                name="贵州茅台",
                currency="CNY",
                exchange="SSE",
                provider_symbol="600519.SH",
                source="tushare",
                is_active=True,
            )
        ][:limit]

    async def get_symbol(
        self,
        *,
        symbol: str,
        market: MarketCode,
    ) -> MarketSymbolCreate:
        return MarketSymbolCreate(
            symbol=symbol,
            market=market,
            name="贵州茅台",
            currency="CNY",
            exchange="SSE",
            provider_symbol="600519.SH",
            source="tushare",
            is_active=True,
        )

    async def get_candles(
        self,
        query: MarketCandleQuery,
    ) -> list[MarketProviderCandle]:
        return [
            MarketProviderCandle(
                symbol=query.symbol,
                market=query.market,
                timeframe=query.timeframe,
                candle_time=datetime.now(UTC) - timedelta(days=query.limit - index),
                open_price=Decimal("100") + Decimal(index),
                high_price=Decimal("101") + Decimal(index),
                low_price=Decimal("99") + Decimal(index),
                close_price=Decimal("100.5") + Decimal(index),
                volume=1000 + index,
                source="tushare",
                adjust_type=query.adjust_type,
            )
            for index in range(query.limit)
        ]


async def test_tushare_provider_search_symbols_uses_stock_basic(monkeypatch) -> None:
    fake_pro = FakeTusharePro()
    monkeypatch.setattr(
        "app.services.market_providers.tushare.get_settings",
        lambda: SimpleNamespace(tushare_token=FakeSecret()),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "tushare",
        SimpleNamespace(pro_api=lambda token: fake_pro),
    )

    result = await TushareProvider().search_symbols(keyword="600519", market="CN")

    assert len(result) == 1
    assert result[0].symbol == "600519"
    assert result[0].name == "贵州茅台"
    assert result[0].provider_symbol == "600519.SH"
    assert fake_pro.stock_basic_calls[0]["list_status"] == "L"
    assert "ts_code,symbol,name" in fake_pro.stock_basic_calls[0]["fields"]


async def test_tushare_provider_get_symbol_uses_stock_basic(monkeypatch) -> None:
    fake_pro = FakeTusharePro()
    monkeypatch.setattr(
        "app.services.market_providers.tushare.get_settings",
        lambda: SimpleNamespace(tushare_token=FakeSecret()),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "tushare",
        SimpleNamespace(pro_api=lambda token: fake_pro),
    )

    result = await TushareProvider().get_symbol(symbol="600519", market="CN")

    assert result.symbol == "600519"
    assert result.name == "贵州茅台"
    assert result.exchange == "SSE"
    assert result.provider_symbol == "600519.SH"
    assert fake_pro.stock_basic_calls[0]["ts_code"] == "600519.SH"


async def test_market_service_search_uses_provider_and_persists_symbol(
    db_session: AsyncSession,
) -> None:
    sync_service = MarketDataSyncService(
        db_session,
        provider=FakeProvider(),
    )
    service = MarketService(
        db_session,
        sync_service=sync_service,
    )

    result = await service.search_stocks(keyword="600519", market="CN")

    assert len(result) == 1
    assert result[0].symbol == "600519"
    assert result[0].name == "贵州茅台"
    assert result[0].exchange == "SSE"

    saved_symbol = await AsyncMarketRepository(db_session).get_symbol(
        symbol="600519",
        market="CN",
    )
    assert saved_symbol is not None
    assert saved_symbol.name == "贵州茅台"
    assert saved_symbol.provider_symbol == "600519.SH"


async def test_market_service_search_refreshes_placeholder_db_symbol(
    db_session: AsyncSession,
) -> None:
    repository = AsyncMarketRepository(db_session)
    await repository.upsert_symbol(
        MarketSymbolCreate(
            symbol="600519",
            market="CN",
            name="600519",
            currency="CNY",
            exchange=None,
            provider_symbol="600519",
            source="mock",
            is_active=True,
        )
    )
    sync_service = MarketDataSyncService(
        db_session,
        provider=FakeProvider(),
    )
    service = MarketService(
        db_session,
        sync_service=sync_service,
    )

    result = await service.search_stocks(keyword="600519", market="CN")

    assert len(result) == 1
    assert result[0].name == "贵州茅台"
    assert result[0].exchange == "SSE"
    assert result[0].source == "tushare"

    saved_symbol = await repository.get_symbol(
        symbol="600519",
        market="CN",
    )
    assert saved_symbol is not None
    assert saved_symbol.name == "贵州茅台"
    assert saved_symbol.source == "tushare"


async def test_market_service_overview_syncs_candles_for_searched_symbol(
    db_session: AsyncSession,
) -> None:
    repository = AsyncMarketRepository(db_session)
    await repository.upsert_symbol(
        MarketSymbolCreate(
            symbol="600519",
            market="CN",
            name="贵州茅台",
            currency="CNY",
            exchange="SSE",
            provider_symbol="600519.SH",
            source="tushare",
            is_active=True,
        )
    )
    sync_service = MarketDataSyncService(
        db_session,
        provider=FakeProvider(),
    )
    service = MarketService(
        db_session,
        sync_service=sync_service,
    )

    overview = await service.get_overview(
        symbol="600519",
        market="CN",
        timeframe="1d",
        limit=5,
    )

    assert overview.quote.name == "贵州茅台"
    assert overview.quote.source == "tushare"
    assert len(overview.candles) == 5
    assert overview.candles[-1].close_price > overview.candles[0].close_price
