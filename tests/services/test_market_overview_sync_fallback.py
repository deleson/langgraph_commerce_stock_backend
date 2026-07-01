from __future__ import annotations

from types import SimpleNamespace

from app.repositories.market_repo import AsyncMarketRepository
from app.schemas.market_data import MarketSymbolCreate
from app.services.market_service import MarketService
from tests.fixtures.quant_data import (
    build_market_symbol_payload,
    build_stale_candles,
    persist_quant_symbol_and_candles,
)


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


async def test_overview_strategy_inherits_data_quality_stale_threshold(
    db_session,
    monkeypatch,
) -> None:
    await persist_quant_symbol_and_candles(
        db_session,
        symbol_payload=build_market_symbol_payload(symbol="QTOVST"),
        candle_payloads=build_stale_candles(symbol="QTOVST", count=40),
    )
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(market_overview_candle_stale_after_days=3650),
    )

    overview = await MarketService(db_session).get_overview(
        symbol="QTOVST",
        market="US",
        timeframe="1d",
        limit=40,
        include_data_quality=True,
        data_quality_source="mock",
        data_quality_min_required=35,
        data_quality_stale_after_days=30,
        include_strategy_signal=True,
        strategy_signal_limit=40,
        strategy_signal_source="mock",
        strategy_signal_min_required=35,
    )

    assert overview.data_quality is not None
    assert overview.data_quality.is_stale is True
    assert overview.strategy_signal is not None
    assert overview.strategy_signal.status == "available"
    assert overview.strategy_signal.signal == "observe"
    assert overview.strategy_signal.score == 40


async def test_overview_explicit_strategy_stale_threshold_takes_precedence(
    db_session,
    monkeypatch,
) -> None:
    await persist_quant_symbol_and_candles(
        db_session,
        symbol_payload=build_market_symbol_payload(symbol="QTOVOV"),
        candle_payloads=build_stale_candles(symbol="QTOVOV", count=40),
    )
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(market_overview_candle_stale_after_days=3650),
    )

    overview = await MarketService(db_session).get_overview(
        symbol="QTOVOV",
        market="US",
        timeframe="1d",
        limit=40,
        include_data_quality=True,
        data_quality_source="mock",
        data_quality_min_required=35,
        data_quality_stale_after_days=30,
        include_strategy_signal=True,
        strategy_signal_limit=40,
        strategy_signal_source="mock",
        strategy_signal_min_required=35,
        strategy_signal_stale_after_days=3650,
    )

    assert overview.data_quality is not None
    assert overview.data_quality.is_stale is True
    assert overview.strategy_signal is not None
    assert overview.strategy_signal.status == "available"
    assert overview.strategy_signal.signal == "buy"
