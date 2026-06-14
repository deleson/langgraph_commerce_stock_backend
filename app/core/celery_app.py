"""Celery 应用配置。

该文件创建后台任务队列使用的 Celery app，并根据配置生成 Beat 定时任务。
Worker 负责执行任务，Beat 负责任务调度。

注意：
生产第一版可以通过配置关闭 Beat，避免每日简报、提醒扫描、纸面交易 tick
等任务在未确认成本和业务频率前自动运行。
"""

from celery import Celery
from celery.schedules import crontab, schedule

from app.core.config import Settings, get_settings

settings = get_settings()

def build_beat_schedule(settings: Settings) -> dict[str, dict]:
    """根据配置生成 Celery Beat 定时任务表。

    只有总开关 `celery_beat_enabled` 和具体任务开关同时开启时，任务才会
    加入 schedule。这样生产环境可以精确控制行情同步、日报、提醒扫描和
    纸面交易 tick 是否自动执行。
    """

    if not settings.celery_beat_enabled:
        return {}

    beat_schedule: dict[str, dict] = {}

    if settings.celery_beat_market_data_sync_enabled:
        # 定时同步行情数据，适合生产环境确认 Provider 和频率后再开启。
        beat_schedule["scheduled-market-data-sync"] = {
            "task": "background_tasks.submit_scheduled_market_data_sync",
            "schedule": schedule(
                run_every=settings.celery_beat_market_data_sync_interval_seconds
            ),
        }

    if settings.celery_beat_daily_report_enabled:
        # 每日简报可能触发 AI 润色，生产开启前需要确认额度和通知策略。
        beat_schedule["scheduled-daily-reports"] = {
            "task": "background_tasks.submit_scheduled_daily_reports",
            "schedule": crontab(
                hour=settings.celery_beat_daily_report_hour,
                minute=settings.celery_beat_daily_report_minute,
            ),
        }

    if settings.celery_beat_quant_alert_scan_enabled:
        # 量化提醒扫描会读取用户规则和行情数据，频率过高会增加外部数据压力。
        beat_schedule["scheduled-quant-alert-scans"] = {
            "task": "background_tasks.submit_scheduled_alert_scans",
            "schedule": schedule(
                run_every=settings.celery_beat_quant_alert_scan_interval_seconds
            ),
        }

    if settings.celery_beat_paper_trading_tick_enabled:
        # 纸面交易 tick 只推进模拟盘，不连接券商，也不会真实下单。
        beat_schedule["scheduled-paper-trading-ticks"] = {
            "task": "background_tasks.submit_scheduled_paper_trading_ticks",
            "schedule": crontab(
                hour=settings.celery_beat_paper_trading_tick_hour,
                minute=settings.celery_beat_paper_trading_tick_minute,
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
