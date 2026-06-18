from types import SimpleNamespace

from app.core.celery_app import build_beat_schedule
from app.tasks import background_tasks


def test_market_symbol_sync_is_added_to_beat_schedule() -> None:
    settings = SimpleNamespace(
        celery_beat_enabled=True,
        celery_beat_market_data_sync_enabled=False,
        celery_beat_market_symbol_sync_enabled=True,
        celery_beat_market_symbol_sync_interval_seconds=3600,
        celery_beat_daily_report_enabled=False,
        celery_beat_quant_alert_scan_enabled=False,
        celery_beat_paper_trading_tick_enabled=False,
    )

    schedule = build_beat_schedule(settings)

    assert "scheduled-market-symbol-sync" in schedule
    assert (
        schedule["scheduled-market-symbol-sync"]["task"]
        == "background_tasks.submit_scheduled_market_symbol_sync"
    )


async def test_submit_scheduled_market_symbol_sync_uses_mock_provider(
    monkeypatch,
) -> None:
    settings = SimpleNamespace(
        celery_beat_market_symbol_sync_provider="mock",
        market_symbol_sync_provider="mock",
        market_data_primary_provider="mock",
        celery_beat_market_symbol_sync_market="US",
        celery_beat_market_symbol_sync_limit=2,
        market_symbol_primary_provider="tushare",
        market_symbol_fallback_providers="baostock,mock",
        baostock_enabled=True,
        tushare_enabled=False,
    )
    monkeypatch.setattr(background_tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(
        "app.services.market_symbol_sync_service.get_settings",
        lambda: settings,
    )

    result = await background_tasks._submit_scheduled_market_symbol_sync_async()

    assert result["status"] == "success"
    assert result["provider"] == "mock"
    assert result["market"] == "US"
    assert result["fetched_count"] == 2
    assert result["source_inserted"] == 2
    assert result["canonical_inserted"] == 2
