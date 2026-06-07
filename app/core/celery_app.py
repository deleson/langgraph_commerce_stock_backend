from celery import Celery
from celery.schedules import crontab, schedule

from app.core.config import Settings, get_settings

settings = get_settings()

def build_beat_schedule(settings: Settings) -> dict[str, dict]:
    if not settings.celery_beat_enabled:
        return {}

    beat_schedule: dict[str, dict] = {}

    if settings.celery_beat_market_data_sync_enabled:
        beat_schedule["scheduled-market-data-sync"] = {
            "task": "background_tasks.submit_scheduled_market_data_sync",
            "schedule": schedule(
                run_every=settings.celery_beat_market_data_sync_interval_seconds
            ),
        }

    if settings.celery_beat_daily_report_enabled:
        beat_schedule["scheduled-daily-reports"] = {
            "task": "background_tasks.submit_scheduled_daily_reports",
            "schedule": crontab(
                hour=settings.celery_beat_daily_report_hour,
                minute=settings.celery_beat_daily_report_minute,
            ),
        }

    if settings.celery_beat_quant_alert_scan_enabled:
        beat_schedule["scheduled-quant-alert-scans"] = {
            "task": "background_tasks.submit_scheduled_alert_scans",
            "schedule": schedule(
                run_every=settings.celery_beat_quant_alert_scan_interval_seconds
            ),
        }

    return beat_schedule

celery_app = Celery(
    "langgraph_commerce",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.background_tasks",
    ],
)

celery_app.conf.update(
    task_default_queue=settings.celery_task_default_queue,
    timezone=settings.celery_timezone,
    enable_utc=settings.celery_enable_utc,
    task_track_started=settings.celery_task_track_started,
    task_time_limit=settings.celery_task_time_limit_seconds,
    task_soft_time_limit=settings.celery_task_soft_time_limit_seconds,
    result_expires=settings.celery_result_expires_seconds,
    beat_schedule=build_beat_schedule(settings),
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)