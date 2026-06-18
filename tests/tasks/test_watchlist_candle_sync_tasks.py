from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery_app import build_beat_schedule
from app.models.background_task import BackgroundTask
from app.tasks import background_tasks


def _settings(**overrides):
    values = {
        "celery_beat_enabled": True,
        "celery_beat_market_data_sync_enabled": False,
        "celery_beat_market_symbol_sync_enabled": False,
        "celery_beat_watchlist_candle_sync_enabled": True,
        "celery_beat_watchlist_candle_sync_hour": 2,
        "celery_beat_watchlist_candle_sync_minute": 15,
        "celery_beat_watchlist_candle_sync_market": "CN",
        "celery_beat_watchlist_candle_sync_timeframe": "1d",
        "celery_beat_watchlist_candle_sync_limit": 120,
        "celery_beat_watchlist_candle_sync_adjust_type": "none",
        "celery_beat_watchlist_candle_sync_source": "mock",
        "celery_beat_watchlist_candle_sync_fallback_sources": "mock",
        "celery_beat_watchlist_candle_sync_max_symbols": 300,
        "celery_beat_watchlist_candle_sync_batch_size": 50,
        "celery_beat_watchlist_candle_sync_stale_after_days": 3,
        "celery_beat_watchlist_candle_sync_max_retries": 2,
        "celery_beat_daily_report_enabled": False,
        "celery_beat_quant_alert_scan_enabled": False,
        "celery_beat_paper_trading_tick_enabled": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_watchlist_candle_sync_is_added_to_beat_schedule() -> None:
    schedule = build_beat_schedule(_settings())

    assert "scheduled-watchlist-candle-sync" in schedule
    assert (
        schedule["scheduled-watchlist-candle-sync"]["task"]
        == "background_tasks.submit_scheduled_watchlist_candle_sync"
    )


async def test_submit_scheduled_watchlist_candle_sync_creates_background_task(
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    calls: list[dict] = []

    def fake_send_task(name: str, args: list[int] | None = None):
        calls.append({"name": name, "args": args or []})
        return SimpleNamespace(id="watchlist-candle-celery-task")

    monkeypatch.setattr(background_tasks, "get_settings", lambda: _settings())
    monkeypatch.setattr(background_tasks.celery_app, "send_task", fake_send_task)

    result = await background_tasks._submit_scheduled_watchlist_candle_sync_async()

    assert result["status"] == "queued"
    assert result["task_type"] == "watchlist_candle_sync"
    assert result["celery_task_id"] == "watchlist-candle-celery-task"
    assert calls == [
        {
            "name": "background_tasks.dispatch_background_task",
            "args": [result["task_id"]],
        }
    ]

    task = await db_session.scalar(
        select(BackgroundTask).where(BackgroundTask.id == result["task_id"])
    )
    assert task is not None
    assert task.task_type == "watchlist_candle_sync"
    assert task.source == "scheduler"
    assert task.payload["market"] == "CN"
    assert task.payload["source"] == "mock"
    assert task.payload["fallback_sources"] == ["mock"]
