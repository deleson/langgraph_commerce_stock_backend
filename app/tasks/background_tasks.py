from __future__ import annotations

import asyncio
from typing import Any

from pydantic import ValidationError

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.repositories.background_task_repo import AsyncBackgroundTaskRepository
from app.schemas.background_task import (
    MarketDataSyncTaskPayload,
    StockAnalysisAsyncTaskPayload,
)
from app.services.market_data_sync_service import MarketDataSyncService


@celery_app.task(name="background_tasks.smoke_test")
def smoke_test() -> dict[str, str]:
    return {
        "status": "ok",
        "message": "celery worker is running",
    }


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

        result = {
            "status": "failed",
            "reason": "stock_analysis_async_reserved",
            "task_type": task.task_type,
            "symbol": payload.symbol,
            "market": payload.market,
            "analysis_type": payload.analysis_type,
            "thread_id": payload.thread_id,
            "notify_when_done": payload.notify_when_done,
            "note": (
                "stock_analysis_async 后台 AI 分析任务已完成任务类型识别和 payload 校验，"
                "但当前步骤只做预留，不调用 DeepSeek，不执行主分析图，"
                "后续步骤会接入 AI 额度检查、失败重试和真实后台分析执行。"
            ),
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
            },
        )

        return {
            "status": failed_task.status,
            "reason": "invalid_stock_analysis_async_payload",
            "task_id": failed_task.id,
            "task_type": failed_task.task_type,
        }

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
        failed_task = await repository.mark_failed(
            task=task,
            error_message=message,
            result={
                "status": "failed",
                "reason": "market_data_sync_failed",
                "task_type": task.task_type,
            },
        )

        return {
            "status": failed_task.status,
            "reason": "market_data_sync_failed",
            "task_id": failed_task.id,
            "task_type": failed_task.task_type,
        }


def _safe_error_message(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        return exc.__class__.__name__
    return message[:1000]