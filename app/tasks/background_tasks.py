from __future__ import annotations

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
    StockAnalysisAsyncTaskPayload,
    UserMemoryEmbeddingRebuildTaskPayload,
    UserProfileRefreshTaskPayload,
)
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
from app.services.user_profile_service import UserProfileService

@celery_app.task(name="background_tasks.smoke_test")
def smoke_test() -> dict[str, str]:
    return {
        "status": "ok",
        "message": "celery worker is running",
    }

BACKGROUND_TASK_RETRY_DELAY_SECONDS = 10
STOCK_ANALYSIS_ASYNC_AI_FEATURE: AIUsageFeature = "stock_analysis"
STOCK_ANALYSIS_ASYNC_ESTIMATED_COMPLETION_TOKENS = 1200

_worker_event_loop: asyncio.AbstractEventLoop | None = None


def _get_worker_event_loop() -> asyncio.AbstractEventLoop:
    global _worker_event_loop

    if _worker_event_loop is None or _worker_event_loop.is_closed():
        _worker_event_loop = asyncio.new_event_loop()

    return _worker_event_loop


@celery_app.task(name="background_tasks.dispatch_background_task")
def dispatch_background_task(task_id: int) -> dict[str, object]:
    loop = _get_worker_event_loop()
    return loop.run_until_complete(_dispatch_background_task_async(task_id))

@celery_app.task(name="background_tasks.submit_scheduled_market_data_sync")
def submit_scheduled_market_data_sync() -> dict[str, object]:
    loop = _get_worker_event_loop()
    return loop.run_until_complete(_submit_scheduled_market_data_sync_async())


async def _submit_scheduled_market_data_sync_async() -> dict[str, object]:
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


async def _dispatch_background_task_async(task_id: int) -> dict[str, object]:
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