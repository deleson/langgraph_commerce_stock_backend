from __future__ import annotations

"""Celery Worker 后台任务执行入口。

本文件是生产环境异步任务的核心：
1. API 或 Celery Beat 先创建 background_tasks 表记录；
2. Celery Worker 收到 task_id；
3. dispatch_background_task 根据 task_type 分发到具体处理器；
4. 处理器执行行情同步、日报、量化提醒、纸面交易 tick 等长任务；
5. 最终把 success / failed / retrying / result / error_message 回写数据库。

这里的任务不是用户直接调用的 HTTP API，而是 Worker 内部执行函数。
"""

import asyncio
from typing import Any

from pydantic import ValidationError

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.repositories.background_task_repo import AsyncBackgroundTaskRepository
from app.schemas.background_task import (
    BackgroundTaskCreateRequest,
    MarketDataSyncTaskPayload,
    PaperTradingTickTaskPayload,
    QuantAlertScanTaskPayload,
    StockAnalysisAsyncTaskPayload,
    UserMemoryEmbeddingRebuildTaskPayload,
    UserProfileRefreshTaskPayload,
)
from app.schemas.daily_report import DailyReportSource, DailyReportTaskPayload
from app.repositories.ai_usage_repo import AsyncAIUsageRepository
from app.schemas.ai_usage import AIQuotaCheckRequest, AIUsageFeature
from app.services.ai_quota_service import AIQuotaService
from app.services.ai_usage_service import AIUsageService
from app.services.ai_usage_token_service import (
    AIUsageCostEstimate,
    AIUsageTokenEstimate,
    AIUsageTokenService,
)
from app.services.market_data_sync_service import MarketDataSyncService
from app.services.user_memory_embedding_service import UserMemoryEmbeddingService
from app.services.user_profile_service import UserProfileService
from app.repositories.user_repo import AsyncUserRepository
from app.services.daily_report_query_service import DailyReportQueryService
from app.schemas.quant_alert import QuantAlertScanRequest, QuantAlertScanSource
from app.services.quant_alert_query_service import QuantAlertQueryService
from app.schemas.paper_trading import PaperTradingTickRequest, PaperTradingTickSource
from app.services.paper_trading_query_service import PaperTradingQueryService

@celery_app.task(name="background_tasks.smoke_test")
def smoke_test() -> dict[str, str]:
    """Worker 存活检查任务，用于生产部署和验收时确认 Celery 可执行。"""

    return {
        "status": "ok",
        "message": "celery worker is running",
    }

BACKGROUND_TASK_RETRY_DELAY_SECONDS = 10
STOCK_ANALYSIS_ASYNC_AI_FEATURE: AIUsageFeature = "stock_analysis"
STOCK_ANALYSIS_ASYNC_ESTIMATED_COMPLETION_TOKENS = 1200

_worker_event_loop: asyncio.AbstractEventLoop | None = None


def _get_worker_event_loop() -> asyncio.AbstractEventLoop:
    """为同步 Celery task 复用一个 asyncio event loop。

    Celery 任务函数本身是同步入口，但项目业务 Service 大多是 async。
    这里统一把 async 任务放到 Worker 进程内的 event loop 中执行。
    """

    global _worker_event_loop

    if _worker_event_loop is None or _worker_event_loop.is_closed():
        _worker_event_loop = asyncio.new_event_loop()

    return _worker_event_loop


@celery_app.task(name="background_tasks.dispatch_background_task")
def dispatch_background_task(task_id: int) -> dict[str, object]:
    """后台任务统一分发入口。

    Celery 只接收 task_id，不直接接收完整 payload。
    这样可以保证任务真实参数来自数据库记录，便于审计、重试和状态追踪。
    """

    loop = _get_worker_event_loop()
    return loop.run_until_complete(_dispatch_background_task_async(task_id))

@celery_app.task(name="background_tasks.submit_scheduled_market_data_sync")
def submit_scheduled_market_data_sync() -> dict[str, object]:
    loop = _get_worker_event_loop()
    return loop.run_until_complete(_submit_scheduled_market_data_sync_async())

@celery_app.task(name="background_tasks.submit_scheduled_daily_reports")
def submit_scheduled_daily_reports() -> dict[str, object]:
    loop = _get_worker_event_loop()
    return loop.run_until_complete(_submit_scheduled_daily_reports_async())

@celery_app.task(name="background_tasks.submit_scheduled_alert_scans")
def submit_scheduled_alert_scans() -> dict[str, object]:
    loop = _get_worker_event_loop()
    return loop.run_until_complete(_submit_scheduled_alert_scans_async())

@celery_app.task(name="background_tasks.submit_scheduled_paper_trading_ticks")
def submit_scheduled_paper_trading_ticks() -> dict[str, object]:
    loop = _get_worker_event_loop()
    return loop.run_until_complete(_submit_scheduled_paper_trading_ticks_async())

async def _submit_scheduled_market_data_sync_async() -> dict[str, object]:
    """由 Celery Beat 触发的行情同步提交器。

    这里不直接同步行情，而是创建一条 market_data_sync 后台任务，
    再交给 dispatch_background_task 统一执行。
    """

    settings = get_settings()

    payload = MarketDataSyncTaskPayload(
        symbol=settings.celery_beat_market_data_sync_symbol,
        market=settings.celery_beat_market_data_sync_market,
        timeframe=settings.celery_beat_market_data_sync_timeframe,
        limit=settings.celery_beat_market_data_sync_limit,
        adjust_type=settings.celery_beat_market_data_sync_adjust_type,
        source=settings.celery_beat_market_data_sync_source,
    )

    request = BackgroundTaskCreateRequest(
        task_type="market_data_sync",
        payload=payload.model_dump(),
        priority="normal",
        source="scheduler",
        max_retries=3,
    )

    async with AsyncSessionLocal() as db:
        repository = AsyncBackgroundTaskRepository(db)
        task = await repository.create_task(
            payload=request,
            user_id=None,
        )

        async_result = celery_app.send_task(
            "background_tasks.dispatch_background_task",
            args=[task.id],
        )

        queued_task = await repository.mark_queued(
            task=task,
            celery_task_id=async_result.id,
        )

        return {
            "status": "queued",
            "reason": "scheduled_market_data_sync_submitted",
            "task_id": queued_task.id,
            "task_type": queued_task.task_type,
            "celery_task_id": queued_task.celery_task_id,
            "symbol": payload.symbol,
            "market": payload.market,
            "timeframe": payload.timeframe,
            "limit": payload.limit,
        }

async def _submit_scheduled_daily_reports_async() -> dict[str, object]:
    """由 Celery Beat 批量提交每日简报任务。

    定时任务会按活跃用户分页创建 daily_report 后台任务。
    这样每个用户的日报都有独立 task_id，失败、重试和结果都能单独追踪。
    """

    settings = get_settings()

    submitted_count = 0
    failed_count = 0
    skipped_count = 0
    submitted_task_ids: list[int] = []
    errors: list[dict[str, object]] = []

    async with AsyncSessionLocal() as db:
        user_repository = AsyncUserRepository(db)
        task_repository = AsyncBackgroundTaskRepository(db)

        offset = 0
        batch_size = settings.celery_beat_daily_report_batch_size

        while True:
            users = await user_repository.list_active_users(
                limit=batch_size,
                offset=offset,
            )

            if not users:
                break

            for user in users:
                payload = DailyReportTaskPayload(
                    use_ai=settings.celery_beat_daily_report_use_ai,
                    force_rebuild=settings.celery_beat_daily_report_force_rebuild,
                    notify=settings.celery_beat_daily_report_notify,
                    include_candidates=settings.celery_beat_daily_report_include_candidates,
                    include_user_profile=settings.celery_beat_daily_report_include_user_profile,
                    include_relevant_memories=settings.celery_beat_daily_report_include_relevant_memories,
                    max_watchlist_items=settings.celery_beat_daily_report_max_watchlist_items,
                    max_candidate_items=settings.celery_beat_daily_report_max_candidate_items,
                    target_user_id=user.id,
                )

                request = BackgroundTaskCreateRequest(
                    task_type="daily_report",
                    payload=payload.model_dump(mode="json", exclude_none=True),
                    priority="normal",
                    source="scheduler",
                    max_retries=settings.celery_beat_daily_report_max_retries,
                )

                try:
                    task = await task_repository.create_task(
                        payload=request,
                        user_id=user.id,
                    )
                    async_result = celery_app.send_task(
                        "background_tasks.dispatch_background_task",
                        args=[task.id],
                    )
                    queued_task = await task_repository.mark_queued(
                        task=task,
                        celery_task_id=async_result.id,
                    )
                    submitted_count += 1
                    submitted_task_ids.append(queued_task.id)
                except Exception as exc:
                    failed_count += 1
                    errors.append(
                        {
                            "user_id": user.id,
                            "error": _safe_error_message(exc),
                        }
                    )

            offset += batch_size

    if submitted_count == 0 and failed_count == 0:
        return {
            "status": "skipped",
            "reason": "no_active_users_for_daily_report",
            "submitted_count": submitted_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
        }

    return {
        "status": "success" if failed_count == 0 else "partial_success",
        "reason": "scheduled_daily_reports_submitted",
        "submitted_count": submitted_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "submitted_task_ids": submitted_task_ids[:50],
        "submitted_task_count": len(submitted_task_ids),
        "errors": errors[:20],
    }

async def _submit_scheduled_alert_scans_async() -> dict[str, object]:
    """由 Celery Beat 批量提交量化提醒扫描任务。"""

    settings = get_settings()

    submitted_count = 0
    failed_count = 0
    skipped_count = 0
    submitted_task_ids: list[int] = []
    errors: list[dict[str, object]] = []

    async with AsyncSessionLocal() as db:
        user_repository = AsyncUserRepository(db)
        task_repository = AsyncBackgroundTaskRepository(db)

        offset = 0
        batch_size = settings.celery_beat_quant_alert_scan_batch_size

        while True:
            users = await user_repository.list_active_users(
                limit=batch_size,
                offset=offset,
            )

            if not users:
                break

            for user in users:
                payload = QuantAlertScanTaskPayload(
                    target_user_id=user.id,
                    source=QuantAlertScanSource.SCHEDULER,
                    notify=settings.celery_beat_quant_alert_scan_notify,
                    force=settings.celery_beat_quant_alert_scan_force,
                    max_watchlist_items=settings.celery_beat_quant_alert_scan_max_watchlist_items,
                )

                request = BackgroundTaskCreateRequest(
                    task_type="alert_scan",
                    payload=payload.model_dump(mode="json", exclude_none=True),
                    priority="normal",
                    source="scheduler",
                    max_retries=settings.celery_beat_quant_alert_scan_max_retries,
                )

                try:
                    task = await task_repository.create_task(
                        payload=request,
                        user_id=user.id,
                    )

                    async_result = celery_app.send_task(
                        "background_tasks.dispatch_background_task",
                        args=[task.id],
                    )

                    queued_task = await task_repository.mark_queued(
                        task=task,
                        celery_task_id=async_result.id,
                    )

                    submitted_count += 1
                    submitted_task_ids.append(queued_task.id)

                except Exception as exc:
                    failed_count += 1
                    errors.append(
                        {
                            "user_id": user.id,
                            "error": _safe_error_message(exc),
                        }
                    )

            offset += batch_size

    if submitted_count == 0 and failed_count == 0:
        return {
            "status": "skipped",
            "reason": "no_active_users_for_alert_scan",
            "submitted_count": submitted_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
        }

    return {
        "status": "success" if failed_count == 0 else "partial_success",
        "reason": "scheduled_alert_scans_submitted",
        "submitted_count": submitted_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "submitted_task_ids": submitted_task_ids[:50],
        "submitted_task_count": len(submitted_task_ids),
        "errors": errors[:20],
    }

async def _submit_scheduled_paper_trading_ticks_async() -> dict[str, object]:
    """由 Celery Beat 批量提交纸面交易 tick 任务。

    纸面交易 tick 会读取用户自选股、策略信号并推进虚拟账户，
    所以必须按用户拆分任务，不能用一个全局任务混在一起执行。
    """

    settings = get_settings()

    submitted_count = 0
    failed_count = 0
    skipped_count = 0
    submitted_task_ids: list[int] = []
    errors: list[dict[str, object]] = []

    async with AsyncSessionLocal() as db:
        user_repository = AsyncUserRepository(db)
        task_repository = AsyncBackgroundTaskRepository(db)

        offset = 0
        batch_size = settings.celery_beat_paper_trading_tick_batch_size

        while True:
            users = await user_repository.list_active_users(
                limit=batch_size,
                offset=offset,
            )

            if not users:
                break

            for user in users:
                payload = PaperTradingTickTaskPayload(
                    target_user_id=user.id,
                    source=PaperTradingTickSource.SCHEDULER,
                    force=settings.celery_beat_paper_trading_tick_force,
                    max_symbols=settings.celery_beat_paper_trading_tick_max_symbols,
                    notify=settings.celery_beat_paper_trading_tick_notify,
                )

                request = BackgroundTaskCreateRequest(
                    task_type="paper_trading_tick",
                    payload=payload.model_dump(mode="json", exclude_none=True),
                    priority="normal",
                    source="scheduler",
                    max_retries=settings.celery_beat_paper_trading_tick_max_retries,
                )

                try:
                    task = await task_repository.create_task(
                        payload=request,
                        user_id=user.id,
                    )

                    async_result = celery_app.send_task(
                        "background_tasks.dispatch_background_task",
                        args=[task.id],
                    )

                    queued_task = await task_repository.mark_queued(
                        task=task,
                        celery_task_id=async_result.id,
                    )

                    submitted_count += 1
                    submitted_task_ids.append(queued_task.id)

                except Exception as exc:
                    failed_count += 1
                    errors.append(
                        {
                            "user_id": user.id,
                            "error": _safe_error_message(exc),
                        }
                    )

            offset += batch_size

    if submitted_count == 0 and failed_count == 0:
        return {
            "status": "skipped",
            "reason": "no_active_users_for_paper_trading_tick",
            "submitted_count": submitted_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
        }

    return {
        "status": "success" if failed_count == 0 else "partial_success",
        "reason": "scheduled_paper_trading_ticks_submitted",
        "submitted_count": submitted_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "submitted_task_ids": submitted_task_ids[:50],
        "submitted_task_count": len(submitted_task_ids),
        "errors": errors[:20],
    }

async def _dispatch_background_task_async(task_id: int) -> dict[str, object]:
    """根据 background_tasks.task_type 分发到具体任务处理器。

    任务执行前先 mark_running；执行成功后由具体处理器 mark_success；
    参数非法、用户不存在等不可重试错误会直接 mark_failed。
    """

    async with AsyncSessionLocal() as db:
        repository = AsyncBackgroundTaskRepository(db)
        task = await repository.get_task(task_id=task_id)

        if task is None:
            return {
                "status": "failed",
                "reason": "task_not_found",
                "task_id": task_id,
            }

        running_task = await repository.mark_running(task=task)

        if running_task.task_type == "market_data_sync":
            return await _run_market_data_sync_task(
                repository=repository,
                task=running_task,
                db=db,
            )

        if running_task.task_type == "stock_analysis_async":
            return await _run_stock_analysis_async_reserved_task(
                repository=repository,
                task=running_task,
            )
        if running_task.task_type == "user_profile_refresh":
            return await _run_user_profile_refresh_task(
                repository=repository,
                task=running_task,
                db=db,
            )

        if running_task.task_type == "user_memory_embedding_rebuild":
            return await _run_user_memory_embedding_rebuild_task(
                repository=repository,
                task=running_task,
                db=db,
            )

        if running_task.task_type == "daily_report":
            return await _run_daily_report_task(
                repository=repository,
                task=running_task,
                db=db,
            )

        if running_task.task_type == "alert_scan":
            return await _run_alert_scan_task(
                repository=repository,
                task=running_task,
                db=db,
            )

        if running_task.task_type == "paper_trading_tick":
            return await _run_paper_trading_tick_task(
                repository=repository,
                task=running_task,
                db=db,
            )

        message = (
            f"后台任务类型 {running_task.task_type} 的执行逻辑尚未接入，"
            "将在后续步骤实现具体任务处理器"
        )

        failed_task = await repository.mark_failed(
            task=running_task,
            error_message=message,
            result={
                "status": "failed",
                "reason": "handler_not_implemented",
                "task_type": running_task.task_type,
                "will_retry": False,
                "retry_count": running_task.retry_count,
                "max_retries": running_task.max_retries,
            },
        )

        return {
            "status": failed_task.status,
            "reason": "handler_not_implemented",
            "task_id": failed_task.id,
            "task_type": failed_task.task_type,
        }

async def _run_stock_analysis_async_reserved_task(
    *,
    repository: AsyncBackgroundTaskRepository,
    task,
) -> dict[str, Any]:
    """预留的异步个股分析任务处理器。

    当前只完成 payload 校验和 AI 额度检查，不真正调用 DeepSeek 和主分析图。
    保留这个处理器是为了让任务类型、额度逻辑和失败记录先稳定下来。
    """

    try:
        payload = StockAnalysisAsyncTaskPayload.model_validate(task.payload)

        if task.user_id is None:
            failed_task = await repository.mark_failed(
                task=task,
                error_message="stock_analysis_async requires user_id for AI quota check",
                result={
                    "status": "failed",
                    "reason": "missing_user_id_for_ai_quota",
                    "task_type": task.task_type,
                    "symbol": payload.symbol,
                    "market": payload.market,
                    "will_retry": False,
                    "retry_count": task.retry_count,
                    "max_retries": task.max_retries,
                },
            )

            return {
                "status": failed_task.status,
                "reason": "missing_user_id_for_ai_quota",
                "task_id": failed_task.id,
                "task_type": failed_task.task_type,
                "symbol": payload.symbol,
                "market": payload.market,
            }

        quota_allowed, quota_reason, estimated_tokens, estimated_cost = (
            await _check_stock_analysis_async_ai_quota(
                repository=repository,
                user_id=task.user_id,
                payload=payload,
            )
        )

        if not quota_allowed:
            usage_log = await _record_stock_analysis_async_ai_blocked(
                repository=repository,
                task=task,
                payload=payload,
                reason=quota_reason or "AI quota exceeded",
                estimated_tokens=estimated_tokens,
                estimated_cost=estimated_cost,
            )

            failed_task = await repository.mark_failed(
                task=task,
                error_message=quota_reason or "AI quota exceeded",
                result={
                    "status": "failed",
                    "reason": "ai_quota_exceeded",
                    "task_type": task.task_type,
                    "symbol": payload.symbol,
                    "market": payload.market,
                    "analysis_type": payload.analysis_type,
                    "thread_id": payload.thread_id,
                    "notify_when_done": payload.notify_when_done,
                    "ai_quota": {
                        "allowed": False,
                        "reason": quota_reason,
                        "feature": STOCK_ANALYSIS_ASYNC_AI_FEATURE,
                        "estimated_prompt_tokens": estimated_tokens.prompt_tokens,
                        "estimated_completion_tokens": estimated_tokens.completion_tokens,
                        "estimated_total_tokens": estimated_tokens.total_tokens,
                        "estimated_cost": str(estimated_cost.estimated_cost),
                        "currency": estimated_cost.currency,
                    },
                    "ai_usage": {
                        "status": "blocked",
                        "usage_log_id": getattr(usage_log, "id", None),
                    },
                    "will_retry": False,
                    "retry_count": task.retry_count,
                    "max_retries": task.max_retries,
                },
            )

            return {
                "status": failed_task.status,
                "reason": "ai_quota_exceeded",
                "task_id": failed_task.id,
                "task_type": failed_task.task_type,
                "symbol": payload.symbol,
                "market": payload.market,
                "ai_usage_log_id": getattr(usage_log, "id", None),
            }

        result = {
            "status": "failed",
            "reason": "stock_analysis_async_reserved",
            "task_type": task.task_type,
            "symbol": payload.symbol,
            "market": payload.market,
            "analysis_type": payload.analysis_type,
            "thread_id": payload.thread_id,
            "notify_when_done": payload.notify_when_done,
            "ai_quota": {
                "allowed": True,
                "reason": None,
                "feature": STOCK_ANALYSIS_ASYNC_AI_FEATURE,
                "estimated_prompt_tokens": estimated_tokens.prompt_tokens,
                "estimated_completion_tokens": estimated_tokens.completion_tokens,
                "estimated_total_tokens": estimated_tokens.total_tokens,
                "estimated_cost": str(estimated_cost.estimated_cost),
                "currency": estimated_cost.currency,
            },
            "note": (
                "stock_analysis_async 后台 AI 分析任务已完成任务类型识别、payload 校验和 AI 额度检查，"
                "但当前步骤仍然只做预留，不调用 DeepSeek，不执行主分析图。"
                "后续步骤会在额度检查、失败重试和真实执行链路稳定后接入后台分析。"
            ),
            "will_retry": False,
            "retry_count": task.retry_count,
            "max_retries": task.max_retries,
        }

        failed_task = await repository.mark_failed(
            task=task,
            error_message="stock_analysis_async task is reserved but not implemented yet",
            result=result,
        )

        return {
            "status": failed_task.status,
            "reason": "stock_analysis_async_reserved",
            "task_id": failed_task.id,
            "task_type": failed_task.task_type,
            "symbol": payload.symbol,
            "market": payload.market,
        }

    except ValidationError as exc:
        message = _safe_error_message(exc)
        failed_task = await repository.mark_failed(
            task=task,
            error_message=message,
            result={
                "status": "failed",
                "reason": "invalid_stock_analysis_async_payload",
                "task_type": task.task_type,
                "will_retry": False,
                "retry_count": task.retry_count,
                "max_retries": task.max_retries,
                "error_type": exc.__class__.__name__,
            },
        )

        return {
            "status": failed_task.status,
            "reason": "invalid_stock_analysis_async_payload",
            "task_id": failed_task.id,
            "task_type": failed_task.task_type,
        }

async def _run_user_profile_refresh_task(
    *,
    repository: AsyncBackgroundTaskRepository,
    task,
    db,
) -> dict[str, Any]:
    """后台刷新用户画像。

    用户画像依赖用户记忆和长期上下文，适合异步执行；
    执行结果会写入 task.result，方便 API 查询任务状态。
    """

    try:
        payload = UserProfileRefreshTaskPayload.model_validate(task.payload)

        if task.user_id is None:
            failed_task = await repository.mark_failed(
                task=task,
                error_message="user_profile_refresh requires user_id",
                result={
                    "status": "failed",
                    "reason": "missing_user_id_for_profile_refresh",
                    "task_type": task.task_type,
                    "will_retry": False,
                    "retry_count": task.retry_count,
                    "max_retries": task.max_retries,
                },
            )

            return {
                "status": failed_task.status,
                "reason": "missing_user_id_for_profile_refresh",
                "task_id": failed_task.id,
                "task_type": failed_task.task_type,
            }

        refresh_result = await UserProfileService(db).refresh_profile(
            user_id=task.user_id,
            request=payload,
        )

        success_task = await repository.mark_success(
            task=task,
            result={
                "status": "success",
                "reason": "user_profile_refresh_completed",
                "task_type": task.task_type,
                "user_id": task.user_id,
                "profile_status": refresh_result.profile.status,
                "profile_version": refresh_result.profile.profile_version,
                "memory_count": refresh_result.memory_count,
                "refreshed": refresh_result.refreshed,
                "message": refresh_result.message,
            },
        )

        return {
            "status": success_task.status,
            "reason": "user_profile_refresh_completed",
            "task_id": success_task.id,
            "task_type": success_task.task_type,
            "profile_version": refresh_result.profile.profile_version,
            "memory_count": refresh_result.memory_count,
        }

    except ValidationError as exc:
        message = _safe_error_message(exc)

        failed_task = await repository.mark_failed(
            task=task,
            error_message=message,
            result={
                "status": "failed",
                "reason": "invalid_user_profile_refresh_payload",
                "task_type": task.task_type,
                "will_retry": False,
                "retry_count": task.retry_count,
                "max_retries": task.max_retries,
                "error_type": exc.__class__.__name__,
            },
        )

        return {
            "status": failed_task.status,
            "reason": "invalid_user_profile_refresh_payload",
            "task_id": failed_task.id,
            "task_type": failed_task.task_type,
        }

    except Exception as exc:
        message = _safe_error_message(exc)

        error_result = {
            "status": "failed",
            "reason": "user_profile_refresh_failed",
            "task_type": task.task_type,
            "error_type": exc.__class__.__name__,
            "error_message": message,
        }

        updated_task, retried = await _mark_failed_or_retry(
            repository=repository,
            task=task,
            error_message=message,
            result=error_result,
            retryable=True,
        )

        return {
            "status": updated_task.status,
            "reason": "user_profile_refresh_retrying"
            if retried
            else "user_profile_refresh_failed",
            "task_id": updated_task.id,
            "task_type": updated_task.task_type,
            "retry_count": updated_task.retry_count,
            "max_retries": updated_task.max_retries,
            "will_retry": retried,
        }

async def _run_user_memory_embedding_rebuild_task(
    *,
    repository: AsyncBackgroundTaskRepository,
    task,
    db,
) -> dict[str, Any]:
    """后台重建用户记忆向量。

    向量生成可能调用外部模型或耗时较长，因此放到 Worker 执行。
    task.user_id 是用户隔离边界，不能只依赖 payload 中的参数。
    """

    try:
        payload = UserMemoryEmbeddingRebuildTaskPayload.model_validate(task.payload)

        if task.user_id is None:
            failed_task = await repository.mark_failed(
                task=task,
                error_message="user_memory_embedding_rebuild requires user_id",
                result={
                    "status": "failed",
                    "reason": "missing_user_id_for_memory_embedding_rebuild",
                    "task_type": task.task_type,
                    "will_retry": False,
                    "retry_count": task.retry_count,
                    "max_retries": task.max_retries,
                },
            )

            return {
                "status": failed_task.status,
                "reason": "missing_user_id_for_memory_embedding_rebuild",
                "task_id": failed_task.id,
                "task_type": failed_task.task_type,
            }

        embedding_service = UserMemoryEmbeddingService(db)

        rebuilt_embeddings = []

        if payload.memory_ids:
            for memory_id in payload.memory_ids:
                rebuilt_embedding = await embedding_service.build_embedding_for_memory(
                    user_id=task.user_id,
                    memory_id=memory_id,
                    build_source="manual_rebuild",
                    force_rebuild=payload.force_rebuild,
                )
                rebuilt_embeddings.append(rebuilt_embedding)
        else:
            rebuilt_embeddings = await embedding_service.build_embeddings_for_user(
                user_id=task.user_id,
                build_source="manual_rebuild",
                force_rebuild=payload.force_rebuild,
            )

        rebuilt_items = [
            {
                "embedding_id": item.id,
                "memory_id": item.memory_id,
                "status": item.status,
                "embedding_provider": item.embedding_provider,
                "embedding_model": item.embedding_model,
                "embedding_dimension": item.embedding_dimension,
                "last_embedded_at": item.last_embedded_at.isoformat()
                if item.last_embedded_at
                else None,
            }
            for item in rebuilt_embeddings
        ]

        success_task = await repository.mark_success(
            task=task,
            result={
                "status": "success",
                "reason": "user_memory_embedding_rebuild_completed",
                "task_type": task.task_type,
                "user_id": task.user_id,
                "requested_memory_ids": payload.memory_ids,
                "rebuilt_count": len(rebuilt_items),
                "rebuilt_items": rebuilt_items[:50],
                "force_rebuild": payload.force_rebuild,
                "only_failed": payload.only_failed,
                "only_stale": payload.only_stale,
                "request_reason": payload.reason,
                "note": (
                    "第一版后台向量刷新复用 UserMemoryEmbeddingService。"
                    "only_failed / only_stale 当前作为请求字段保留，后续可进一步细化筛选逻辑。"
                ),
            },
        )

        return {
            "status": success_task.status,
            "reason": "user_memory_embedding_rebuild_completed",
            "task_id": success_task.id,
            "task_type": success_task.task_type,
            "rebuilt_count": len(rebuilt_items),
        }

    except ValidationError as exc:
        message = _safe_error_message(exc)

        failed_task = await repository.mark_failed(
            task=task,
            error_message=message,
            result={
                "status": "failed",
                "reason": "invalid_user_memory_embedding_rebuild_payload",
                "task_type": task.task_type,
                "will_retry": False,
                "retry_count": task.retry_count,
                "max_retries": task.max_retries,
                "error_type": exc.__class__.__name__,
            },
        )

        return {
            "status": failed_task.status,
            "reason": "invalid_user_memory_embedding_rebuild_payload",
            "task_id": failed_task.id,
            "task_type": failed_task.task_type,
        }

    except Exception as exc:
        message = _safe_error_message(exc)

        error_result = {
            "status": "failed",
            "reason": "user_memory_embedding_rebuild_failed",
            "task_type": task.task_type,
            "error_type": exc.__class__.__name__,
            "error_message": message,
        }

        updated_task, retried = await _mark_failed_or_retry(
            repository=repository,
            task=task,
            error_message=message,
            result=error_result,
            retryable=True,
        )

        return {
            "status": updated_task.status,
            "reason": "user_memory_embedding_rebuild_retrying"
            if retried
            else "user_memory_embedding_rebuild_failed",
            "task_id": updated_task.id,
            "task_type": updated_task.task_type,
            "retry_count": updated_task.retry_count,
            "max_retries": updated_task.max_retries,
            "will_retry": retried,
        }

async def _run_daily_report_task(
    *,
    repository: AsyncBackgroundTaskRepository,
    task,
    db,
) -> dict[str, Any]:
    """执行单个用户的每日简报生成任务。

    这个处理器复用 DailyReportQueryService，确保 API 手动生成和后台定时生成
    走同一套日报数据收集、确定性报告、AI 润色和通知逻辑。
    """

    try:
        payload = DailyReportTaskPayload.model_validate(task.payload)

        if task.user_id is None and payload.target_user_id is None:
            failed_task = await repository.mark_failed(
                task=task,
                error_message="daily_report requires user_id or target_user_id",
                result={
                    "status": "failed",
                    "reason": "missing_user_id_for_daily_report",
                    "task_type": task.task_type,
                    "will_retry": False,
                    "retry_count": task.retry_count,
                    "max_retries": task.max_retries,
                },
            )

            return {
                "status": failed_task.status,
                "reason": "missing_user_id_for_daily_report",
                "task_id": failed_task.id,
                "task_type": failed_task.task_type,
            }

        target_user_id = task.user_id or payload.target_user_id
        user = await AsyncUserRepository(db).get_by_id(target_user_id)

        if user is None:
            failed_task = await repository.mark_failed(
                task=task,
                error_message="daily report target user not found",
                result={
                    "status": "failed",
                    "reason": "daily_report_user_not_found",
                    "task_type": task.task_type,
                    "target_user_id": target_user_id,
                    "will_retry": False,
                    "retry_count": task.retry_count,
                    "max_retries": task.max_retries,
                },
            )

            return {
                "status": failed_task.status,
                "reason": "daily_report_user_not_found",
                "task_id": failed_task.id,
                "task_type": failed_task.task_type,
                "target_user_id": target_user_id,
            }

        request = DailyReportTaskPayload(
            report_date=payload.report_date,
            use_ai=payload.use_ai,
            force_rebuild=payload.force_rebuild,
            notify=payload.notify,
            include_candidates=payload.include_candidates,
            include_user_profile=payload.include_user_profile,
            include_relevant_memories=payload.include_relevant_memories,
            max_watchlist_items=payload.max_watchlist_items,
            max_candidate_items=payload.max_candidate_items,
            target_user_id=target_user_id,
        )

        generation_result = await DailyReportQueryService(db).generate_daily_report(
            user=user,
            request=request,
            source=(
                DailyReportSource.SCHEDULER
                if task.source == "scheduler"
                else DailyReportSource.BACKGROUND_TASK
            ),
        )

        success_task = await repository.mark_success(
            task=task,
            result={
                "status": "success",
                "reason": "daily_report_completed",
                "task_type": task.task_type,
                "target_user_id": target_user_id,
                "report_id": generation_result.report.id,
                "report_date": generation_result.report.report_date.isoformat(),
                "report_status": generation_result.report.status,
                "created": generation_result.created,
                "ai_used": generation_result.ai_used,
                "fallback_used": generation_result.fallback_used,
                "notification_created": generation_result.notification_created,
                "notification_id": generation_result.report.notification_id,
            },
        )

        return {
            "status": success_task.status,
            "reason": "daily_report_completed",
            "task_id": success_task.id,
            "task_type": success_task.task_type,
            "target_user_id": target_user_id,
            "report_id": generation_result.report.id,
            "report_status": generation_result.report.status,
        }

    except ValidationError as exc:
        message = _safe_error_message(exc)

        failed_task = await repository.mark_failed(
            task=task,
            error_message=message,
            result={
                "status": "failed",
                "reason": "invalid_daily_report_payload",
                "task_type": task.task_type,
                "will_retry": False,
                "retry_count": task.retry_count,
                "max_retries": task.max_retries,
                "error_type": exc.__class__.__name__,
            },
        )

        return {
            "status": failed_task.status,
            "reason": "invalid_daily_report_payload",
            "task_id": failed_task.id,
            "task_type": task.task_type,
        }

    except Exception as exc:
        message = _safe_error_message(exc)

        error_result = {
            "status": "failed",
            "reason": "daily_report_failed",
            "task_type": task.task_type,
            "error_type": exc.__class__.__name__,
            "error_message": message,
        }

        updated_task, retried = await _mark_failed_or_retry(
            repository=repository,
            task=task,
            error_message=message,
            result=error_result,
            retryable=True,
        )

        return {
            "status": updated_task.status,
            "reason": "daily_report_retrying" if retried else "daily_report_failed",
            "task_id": updated_task.id,
            "task_type": updated_task.task_type,
            "retry_count": updated_task.retry_count,
            "max_retries": updated_task.max_retries,
            "will_retry": retried,
        }

async def _run_alert_scan_task(
    *,
    repository: AsyncBackgroundTaskRepository,
    task,
    db,
) -> dict[str, Any]:
    """执行单个用户的量化提醒扫描任务。

    后台任务和 API 手动扫描复用 QuantAlertQueryService，
    确保规则读取、数据收集、事件去重和通知创建只有一套实现。
    """

    try:
        payload = QuantAlertScanTaskPayload.model_validate(task.payload)

        if task.user_id is None and payload.target_user_id is None:
            failed_task = await repository.mark_failed(
                task=task,
                error_message="alert_scan requires user_id or target_user_id",
                result={
                    "status": "failed",
                    "reason": "missing_user_id_for_alert_scan",
                    "task_type": task.task_type,
                    "will_retry": False,
                    "retry_count": task.retry_count,
                    "max_retries": task.max_retries,
                },
            )

            return {
                "status": failed_task.status,
                "reason": "missing_user_id_for_alert_scan",
                "task_id": failed_task.id,
                "task_type": failed_task.task_type,
            }

        target_user_id = task.user_id or payload.target_user_id
        user = await AsyncUserRepository(db).get_by_id(target_user_id)

        if user is None:
            failed_task = await repository.mark_failed(
                task=task,
                error_message="alert scan target user not found",
                result={
                    "status": "failed",
                    "reason": "alert_scan_user_not_found",
                    "task_type": task.task_type,
                    "target_user_id": target_user_id,
                    "will_retry": False,
                    "retry_count": task.retry_count,
                    "max_retries": task.max_retries,
                },
            )

            return {
                "status": failed_task.status,
                "reason": "alert_scan_user_not_found",
                "task_id": failed_task.id,
                "task_type": failed_task.task_type,
                "target_user_id": target_user_id,
            }

        request = QuantAlertScanRequest(
            target_user_id=target_user_id,
            symbols=payload.symbols,
            market=payload.market,
            rule_types=payload.rule_types,
            source=(
                QuantAlertScanSource.SCHEDULER
                if task.source == "scheduler"
                else QuantAlertScanSource.BACKGROUND_TASK
            ),
            notify=payload.notify,
            force=payload.force,
            max_watchlist_items=payload.max_watchlist_items,
        )

        scan_result = await QuantAlertQueryService(db).scan_alerts(
            user=user,
            request=request,
        )

        success_task = await repository.mark_success(
            task=task,
            result={
                "status": "success",
                "reason": "alert_scan_completed",
                "task_type": task.task_type,
                "target_user_id": target_user_id,
                "scan_status": scan_result.status,
                "unavailable_reason": scan_result.unavailable_reason,
                "scanned_count": scan_result.scanned_count,
                "triggered_count": scan_result.triggered_count,
                "notification_count": scan_result.notification_count,
                "summary": scan_result.summary,
                "warnings": scan_result.warnings[:20],
            },
        )

        return {
            "status": success_task.status,
            "reason": "alert_scan_completed",
            "task_id": success_task.id,
            "task_type": success_task.task_type,
            "target_user_id": target_user_id,
            "scanned_count": scan_result.scanned_count,
            "triggered_count": scan_result.triggered_count,
            "notification_count": scan_result.notification_count,
        }

    except ValidationError as exc:
        message = _safe_error_message(exc)

        failed_task = await repository.mark_failed(
            task=task,
            error_message=message,
            result={
                "status": "failed",
                "reason": "invalid_alert_scan_payload",
                "task_type": task.task_type,
                "will_retry": False,
                "retry_count": task.retry_count,
                "max_retries": task.max_retries,
                "error_type": exc.__class__.__name__,
            },
        )

        return {
            "status": failed_task.status,
            "reason": "invalid_alert_scan_payload",
            "task_id": failed_task.id,
            "task_type": task.task_type,
        }

    except Exception as exc:
        message = _safe_error_message(exc)

        error_result = {
            "status": "failed",
            "reason": "alert_scan_failed",
            "task_type": task.task_type,
            "error_type": exc.__class__.__name__,
            "error_message": message,
        }

        updated_task, retried = await _mark_failed_or_retry(
            repository=repository,
            task=task,
            error_message=message,
            result=error_result,
            retryable=True,
        )

        return {
            "status": updated_task.status,
            "reason": "alert_scan_retrying" if retried else "alert_scan_failed",
            "task_id": updated_task.id,
            "task_type": updated_task.task_type,
            "retry_count": updated_task.retry_count,
            "max_retries": updated_task.max_retries,
            "will_retry": retried,
        }

async def _run_paper_trading_tick_task(
    *,
    repository: AsyncBackgroundTaskRepository,
    task,
    db,
) -> dict[str, Any]:
    """执行单个用户的纸面交易 tick 后台任务。

    任务会强制解析目标用户，并把 source 映射成 background_task 或 scheduler。
    真正的信号读取、订单、成交、持仓和权益快照仍然由 PaperTradingQueryService.run_tick 编排。
    """

    try:
        payload = PaperTradingTickTaskPayload.model_validate(task.payload)

        if task.user_id is None and payload.target_user_id is None:
            failed_task = await repository.mark_failed(
                task=task,
                error_message="paper_trading_tick requires user_id or target_user_id",
                result={
                    "status": "failed",
                    "reason": "missing_user_id_for_paper_trading_tick",
                    "task_type": task.task_type,
                    "will_retry": False,
                    "retry_count": task.retry_count,
                    "max_retries": task.max_retries,
                },
            )

            return {
                "status": failed_task.status,
                "reason": "missing_user_id_for_paper_trading_tick",
                "task_id": failed_task.id,
                "task_type": failed_task.task_type,
            }

        target_user_id = task.user_id or payload.target_user_id
        user = await AsyncUserRepository(db).get_by_id(target_user_id)

        if user is None:
            failed_task = await repository.mark_failed(
                task=task,
                error_message="paper trading tick target user not found",
                result={
                    "status": "failed",
                    "reason": "paper_trading_tick_user_not_found",
                    "task_type": task.task_type,
                    "target_user_id": target_user_id,
                    "will_retry": False,
                    "retry_count": task.retry_count,
                    "max_retries": task.max_retries,
                },
            )

            return {
                "status": failed_task.status,
                "reason": "paper_trading_tick_user_not_found",
                "task_id": failed_task.id,
                "task_type": failed_task.task_type,
                "target_user_id": target_user_id,
            }

        request = PaperTradingTickRequest(
            account_id=payload.account_id,
            target_user_id=target_user_id,
            source=(
                PaperTradingTickSource.SCHEDULER
                if task.source == "scheduler"
                else PaperTradingTickSource.BACKGROUND_TASK
            ),
            force=payload.force,
            max_symbols=payload.max_symbols,
            notify=payload.notify,
        )

        tick_result = await PaperTradingQueryService(db).run_tick(
            user=user,
            request=request,
        )

        resolved_account_id = (
            tick_result.account.id
            if tick_result.account is not None
            else payload.account_id
        )

        input_snapshot = tick_result.input_snapshot
        equity_snapshot = tick_result.equity_snapshot

        paper_trading_result = _build_paper_trading_tick_task_result(
            task=task,
            target_user_id=target_user_id,
            account_id=resolved_account_id,
            tick_result=tick_result,
        )

        success_task = await repository.mark_success(
            task=task,
            result=paper_trading_result,
        )

        return {
            "status": success_task.status,
            "reason": "paper_trading_tick_completed",
            "task_id": success_task.id,
            "task_type": success_task.task_type,
            "target_user_id": target_user_id,
            "tick_status": tick_result.status,
            "account_id": resolved_account_id,
            "run_id": tick_result.run_id,
            "paper_trading_run_id": tick_result.run_id,
        }

    except ValidationError as exc:
        message = _safe_error_message(exc)

        failed_task = await repository.mark_failed(
            task=task,
            error_message=message,
            result={
                "status": "failed",
                "reason": "invalid_paper_trading_tick_payload",
                "task_type": task.task_type,
                "will_retry": False,
                "retry_count": task.retry_count,
                "max_retries": task.max_retries,
                "error_type": exc.__class__.__name__,
            },
        )

        return {
            "status": failed_task.status,
            "reason": "invalid_paper_trading_tick_payload",
            "task_id": failed_task.id,
            "task_type": task.task_type,
        }

    except Exception as exc:
        message = _safe_error_message(exc)

        error_result = {
            "status": "failed",
            "reason": "paper_trading_tick_failed",
            "task_type": task.task_type,
            "error_type": exc.__class__.__name__,
            "error_message": message,
        }

        updated_task, retried = await _mark_failed_or_retry(
            repository=repository,
            task=task,
            error_message=message,
            result=error_result,
            retryable=True,
        )

        return {
            "status": updated_task.status,
            "reason": (
                "paper_trading_tick_retrying"
                if retried
                else "paper_trading_tick_failed"
            ),
            "task_id": updated_task.id,
            "task_type": updated_task.task_type,
            "retry_count": updated_task.retry_count,
            "max_retries": updated_task.max_retries,
            "will_retry": retried,
        }

def _build_paper_trading_tick_task_result(
    *,
    task,
    target_user_id: int,
    account_id: int | None,
    tick_result,
) -> dict[str, Any]:
    """构造写入 background_tasks.result 的纸面交易 tick 摘要。

    result 中会保留 run_id、订单数、成交数、扫描数和运行记录路径，
    方便前端从后台任务跳转到纸面交易运行详情。
    """

    input_snapshot = tick_result.input_snapshot
    equity_snapshot = tick_result.equity_snapshot

    result: dict[str, Any] = {
        "status": "success",
        "reason": "paper_trading_tick_completed",
        "task_type": task.task_type,
        "target_user_id": target_user_id,
        "tick_status": tick_result.status,
        "unavailable_reason": tick_result.unavailable_reason,
        "account_id": account_id,
        "run_id": tick_result.run_id,
        "paper_trading_run_id": tick_result.run_id,
        "order_count": (
            input_snapshot.order_count
            if input_snapshot is not None
            else 0
        ),
        "trade_count": (
            input_snapshot.trade_count
            if input_snapshot is not None
            else 0
        ),
        "scanned_count": (
            input_snapshot.scanned_count
            if input_snapshot is not None
            else 0
        ),
        "effective_max_symbols": (
            input_snapshot.scanned_count
            if input_snapshot is not None
            else None
        ),
        "equity_snapshot_id": (
            equity_snapshot.id
            if equity_snapshot is not None
            else None
        ),
        "has_equity_snapshot": equity_snapshot is not None,
        "warning_count": len(tick_result.warnings),
        "warnings": tick_result.warnings[:20],
        "tick_generated_at": tick_result.generated_at.isoformat(),
    }

    if account_id is not None:
        result["run_list_path"] = _build_paper_trading_run_list_path(
            account_id=account_id,
        )

        if tick_result.run_id is not None:
            result["run_detail_path"] = _build_paper_trading_run_detail_path(
                account_id=account_id,
                run_id=tick_result.run_id,
            )

    return result

def _build_paper_trading_run_list_path(
    *,
    account_id: int,
) -> str:
    return f"/api/v1/paper-trading/accounts/{account_id}/runs"


def _build_paper_trading_run_detail_path(
    *,
    account_id: int,
    run_id: int,
) -> str:
    return f"/api/v1/paper-trading/accounts/{account_id}/runs/{run_id}"

async def _check_stock_analysis_async_ai_quota(
    *,
    repository: AsyncBackgroundTaskRepository,
    user_id: int,
    payload: StockAnalysisAsyncTaskPayload,
) -> tuple[bool, str | None, AIUsageTokenEstimate, AIUsageCostEstimate]:
    token_service = AIUsageTokenService()
    settings = get_settings()

    prompt_text = _build_stock_analysis_async_quota_prompt(payload)
    prompt_tokens = token_service.estimate_tokens_from_text(prompt_text)

    estimated_tokens = AIUsageTokenEstimate(
        prompt_tokens=prompt_tokens,
        completion_tokens=STOCK_ANALYSIS_ASYNC_ESTIMATED_COMPLETION_TOKENS,
        total_tokens=prompt_tokens + STOCK_ANALYSIS_ASYNC_ESTIMATED_COMPLETION_TOKENS,
        token_source="estimated",
    )
    estimated_cost = token_service.estimate_cost(
        model_name=settings.llm_model,
        prompt_tokens=estimated_tokens.prompt_tokens,
        completion_tokens=estimated_tokens.completion_tokens,
    )

    ai_usage_repo = AsyncAIUsageRepository(repository.db)
    quota_service = AIQuotaService(ai_usage_repo)

    quota_result = await quota_service.check_quota(
        AIQuotaCheckRequest(
            user_id=user_id,
            feature=STOCK_ANALYSIS_ASYNC_AI_FEATURE,
            provider="deepseek",
            model_name=settings.llm_model,
            estimated_prompt_tokens=estimated_tokens.prompt_tokens,
            estimated_completion_tokens=estimated_tokens.completion_tokens,
            estimated_total_tokens=estimated_tokens.total_tokens,
            estimated_cost=estimated_cost.estimated_cost,
            currency=estimated_cost.currency,
        )
    )

    return (
        quota_result.allowed,
        quota_result.reason,
        estimated_tokens,
        estimated_cost,
    )

async def _record_stock_analysis_async_ai_blocked(
    *,
    repository: AsyncBackgroundTaskRepository,
    task,
    payload: StockAnalysisAsyncTaskPayload,
    reason: str,
    estimated_tokens: AIUsageTokenEstimate,
    estimated_cost: AIUsageCostEstimate,
):
    if task.user_id is None:
        return None

    ai_usage_repo = AsyncAIUsageRepository(repository.db)
    usage_service = AIUsageService(ai_usage_repo)

    return await usage_service.record_blocked(
        user_id=task.user_id,
        feature=STOCK_ANALYSIS_ASYNC_AI_FEATURE,
        model_name=get_settings().llm_model,
        reason=reason,
        estimated_prompt_tokens=estimated_tokens.prompt_tokens,
        estimated_completion_tokens=estimated_tokens.completion_tokens,
        estimated_cost=estimated_cost.estimated_cost,
        analysis_thread_id=payload.thread_id,
        extra={
            "source": "background_task",
            "background_task_id": task.id,
            "background_task_type": task.task_type,
            "symbol": payload.symbol,
            "market": payload.market,
            "analysis_type": payload.analysis_type,
        },
    )

def _build_stock_analysis_async_quota_prompt(
    payload: StockAnalysisAsyncTaskPayload,
) -> str:
    return "\n".join(
        [
            "Background stock analysis task quota estimate.",
            f"symbol: {payload.symbol}",
            f"market: {payload.market}",
            f"analysis_type: {payload.analysis_type}",
            f"thread_id: {payload.thread_id or ''}",
            f"notify_when_done: {payload.notify_when_done}",
        ]
    )

async def _run_market_data_sync_task(
    *,
    repository: AsyncBackgroundTaskRepository,
    task,
    db,
) -> dict[str, Any]:
    """执行行情同步后台任务。

    该处理器只负责把 MarketDataSyncTaskPayload 转交给 MarketDataSyncService，
    成功或失败都会回写 background_tasks，便于生产环境排查 Provider 问题。
    """

    try:
        payload = MarketDataSyncTaskPayload.model_validate(task.payload)

        candles = await MarketDataSyncService(db).sync_candles(
            symbol=payload.symbol,
            market=payload.market,
            timeframe=payload.timeframe,
            limit=payload.limit,
            adjust_type=payload.adjust_type,
        )

        result = {
            "status": "success",
            "task_type": task.task_type,
            "symbol": payload.symbol,
            "market": payload.market,
            "timeframe": payload.timeframe,
            "adjust_type": payload.adjust_type,
            "requested_source": payload.source,
            "actual_source": candles[0].source if candles else None,
            "synced_count": len(candles),
            "first_candle_time": candles[0].candle_time.isoformat() if candles else None,
            "last_candle_time": candles[-1].candle_time.isoformat() if candles else None,
            "note": (
                "第一版后台市场数据同步复用 MarketDataSyncService；"
                "source / start_date / end_date / force_refresh 暂作为参数预留"
            ),
        }

        success_task = await repository.mark_success(
            task=task,
            result=result,
        )

        return {
            "status": success_task.status,
            "reason": "market_data_sync_completed",
            "task_id": success_task.id,
            "task_type": success_task.task_type,
            "synced_count": len(candles),
        }

    except ValidationError as exc:
        message = _safe_error_message(exc)
        failed_task = await repository.mark_failed(
            task=task,
            error_message=message,
            result={
                "status": "failed",
                "reason": "invalid_market_data_sync_payload",
                "task_type": task.task_type,
                "will_retry": False,
                "retry_count": task.retry_count,
                "max_retries": task.max_retries,
                "error_type": exc.__class__.__name__,
            },
        )

        return {
            "status": failed_task.status,
            "reason": "invalid_market_data_sync_payload",
            "task_id": failed_task.id,
            "task_type": failed_task.task_type,
        }

    except Exception as exc:
        message = _safe_error_message(exc)

        error_result = {
            "status": "failed",
            "reason": "market_data_sync_failed",
            "task_type": task.task_type,
            "error_type": exc.__class__.__name__,
            "error_message": message,
        }

        updated_task, retried = await _mark_failed_or_retry(
            repository=repository,
            task=task,
            error_message=message,
            result=error_result,
            retryable=True,
        )

        return {
            "status": updated_task.status,
            "reason": "market_data_sync_retrying" if retried else "market_data_sync_failed",
            "task_id": updated_task.id,
            "task_type": updated_task.task_type,
            "retry_count": updated_task.retry_count,
            "max_retries": updated_task.max_retries,
            "will_retry": retried,
        }


def _can_retry_task(task) -> bool:
    return task.retry_count < task.max_retries

async def _mark_failed_or_retry(
    *,
    repository: AsyncBackgroundTaskRepository,
    task,
    error_message: str,
    result: dict[str, Any],
    retryable: bool,
) -> tuple[object, bool]:
    """根据任务重试配置把任务标记为 retrying 或 failed。

    payload 校验失败、用户不存在等不可恢复错误不应重试；
    外部服务异常、行情源波动等可恢复错误才允许进入 retrying。
    """

    if retryable and _can_retry_task(task):
        retrying_task = await repository.mark_retrying(
            task=task,
            error_message=error_message,
        )

        async_result = celery_app.send_task(
            "background_tasks.dispatch_background_task",
            args=[retrying_task.id],
            countdown=BACKGROUND_TASK_RETRY_DELAY_SECONDS,
        )

        queued_task = await repository.mark_queued(
            task=retrying_task,
            celery_task_id=async_result.id,
        )

        queued_task.result = {
            **result,
            "status": "retrying",
            "will_retry": True,
            "retry_count": queued_task.retry_count,
            "max_retries": queued_task.max_retries,
            "next_retry_delay_seconds": BACKGROUND_TASK_RETRY_DELAY_SECONDS,
        }
        repository.db.add(queued_task)
        await repository.db.commit()
        await repository.db.refresh(queued_task)

        return queued_task, True

    failed_task = await repository.mark_failed(
        task=task,
        error_message=error_message,
        result={
            **result,
            "status": "failed",
            "will_retry": False,
            "retry_count": task.retry_count,
            "max_retries": task.max_retries,
        },
    )

    return failed_task, False

def _safe_error_message(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        return exc.__class__.__name__
    return message[:1000]
