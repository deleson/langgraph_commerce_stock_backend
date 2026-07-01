from __future__ import annotations

from types import SimpleNamespace

from app.repositories.market_repo import AsyncMarketRepository
from app.schemas.market_data import MarketSymbolCreate
from app.services.market_service import MarketService


async def test_overview_sync_continues_to_fallback_when_provider_returns_no_candles(
    db_session,
    monkeypatch,
) -> None:
    repository = AsyncMarketRepository(db_session)
    await repository.upsert_symbol(
        MarketSymbolCreate(
            symbol="000018",
            market="CN",
            name="神城A退",
            currency="CNY",
            exchange="SZSE",
            provider_symbol="sz.000018",
            source="baostock",
            is_active=False,
        )
    )

    calls: list[str] = []

    class _SyncService:
        def __init__(self, _db, *, provider_name: str) -> None:
            self.provider_name = provider_name

        async def sync_candles(self, **_kwargs):
            calls.append(self.provider_name)
            return [] if self.provider_name == "primary" else [object()]

    settings = SimpleNamespace(
        market_overview_candle_stale_after_days=3,
        celery_beat_watchlist_candle_sync_source="primary",
        market_data_primary_provider="primary",
        celery_beat_watchlist_candle_sync_fallback_sources="fallback",
    )
    monkeypatch.setattr(
        "app.services.market_service.MarketDataSyncService",
        _SyncService,
    )
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)

    await MarketService(
        db_session,
        repository=repository,
    )._ensure_candles_for_overview(
        symbol="000018",
        market="CN",
        timeframe="1d",
        limit=60,
        include_technical_indicators=True,
        technical_indicator_limit=120,
        include_strategy_signal=True,
        strategy_signal_limit=120,
        adjust_type="none",
    )

    assert calls == ["primary", "fallback"]
