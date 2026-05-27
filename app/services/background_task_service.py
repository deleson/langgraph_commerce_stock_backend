from __future__ import annotations

from typing import Any

from celery import Celery
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery_app import celery_app
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.background_task import BackgroundTask
from app.repositories.background_task_repo import AsyncBackgroundTaskRepository
from app.schemas.background_task import (
    BackgroundTaskCreateRequest,
    BackgroundTaskListQuery,
    BackgroundTaskListResponse,
    BackgroundTaskResponse,
    BackgroundTaskSubmitResponse,
)


class BackgroundTaskService:
    DISPATCH_TASK_NAME = "background_tasks.dispatch_background_task"
    TERMINAL_STATUSES = {"success", "failed", "cancelled"}

    def __init__(
        self,
        db: AsyncSession,
        *,
        repository: AsyncBackgroundTaskRepository | None = None,
        celery: Celery | None = None,
    ) -> None:
        self.db = db
        self.repository = repository or AsyncBackgroundTaskRepository(db)
        self.celery_app = celery or celery_app

    async def submit_task(
        self,
        *,
        request: BackgroundTaskCreateRequest,
        user_id: int | None = None,
    ) -> BackgroundTaskSubmitResponse:
        task = await self.repository.create_task(
            payload=request,
            user_id=user_id,
        )

        try:
            async_result = self.celery_app.send_task(
                self.DISPATCH_TASK_NAME,
                args=[task.id],
            )
        except Exception as exc:
            await self.repository.mark_failed(
                task=task,
                error_message=self._safe_error_message(exc),
                result={
                    "status": "failed",
                    "reason": "celery_submit_failed",
                },
            )
            raise BadRequestException(
                message="后台任务投递失败，请确认 Redis 和 Celery Worker 配置是否可用"
            ) from exc

        queued_task = await self.repository.mark_queued(
            task=task,
            celery_task_id=async_result.id,
        )

        return BackgroundTaskSubmitResponse(
            task_id=queued_task.id,
            task_type=queued_task.task_type,
            status=queued_task.status,
            celery_task_id=queued_task.celery_task_id,
            message="后台任务已提交，正在等待 Worker 执行",
        )

    async def get_task(
        self,
        *,
        task_id: int,
        user_id: int | None = None,
    ) -> BackgroundTaskResponse:
        task = await self._get_task_or_raise(task_id=task_id)

        if user_id is not None and task.user_id != user_id:
            raise NotFoundException(message="后台任务不存在")

        return self._build_task_response(task)

    async def list_tasks(
        self,
        *,
        query: BackgroundTaskListQuery,
        user_id: int | None = None,
    ) -> BackgroundTaskListResponse:
        tasks = await self.repository.list_tasks(
            query=query,
            user_id=user_id,
        )
        total = await self.repository.count_tasks(
            query=query,
            user_id=user_id,
        )

        return BackgroundTaskListResponse(
            items=[self._build_task_response(task) for task in tasks],
            total=total,
            limit=query.limit,
            offset=query.offset,
        )

    async def cancel_task(
        self,
        *,
        task_id: int,
        user_id: int | None = None,
    ) -> BackgroundTaskResponse:
        task = await self._get_task_or_raise(task_id=task_id)

        if user_id is not None and task.user_id != user_id:
            raise NotFoundException(message="后台任务不存在")

        if task.status in self.TERMINAL_STATUSES:
            raise BadRequestException(message="已结束的后台任务不能取消")

        cancelled_task = await self.repository.mark_cancelled(
            task=task,
            error_message="任务已被取消",
        )
        return self._build_task_response(cancelled_task)

    async def _get_task_or_raise(
        self,
        *,
        task_id: int,
    ) -> BackgroundTask:
        task = await self.repository.get_task(task_id=task_id)
        if task is None:
            raise NotFoundException(message="后台任务不存在")
        return task

    def _build_task_response(
        self,
        task: BackgroundTask,
    ) -> BackgroundTaskResponse:
        return BackgroundTaskResponse.model_validate(task)

    def _safe_error_message(
        self,
        exc: Exception,
    ) -> str:
        message = str(exc).strip()
        if not message:
            return exc.__class__.__name__
        return message[:1000]