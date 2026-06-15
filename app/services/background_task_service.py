from __future__ import annotations

"""后台任务 API 侧编排服务。

本文件负责“用户通过 API 提交后台任务”这一侧的业务：
1. 先把任务请求写入 background_tasks 表；
2. 再把任务 id 投递给 Celery Worker；
3. 后续任务执行状态由 Worker 回写数据库。

注意：这里不直接执行耗时业务逻辑，避免 HTTP 请求被行情同步、日报生成、
纸面交易 tick 等长任务阻塞。
"""

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
    """后台任务提交、查询、列表和取消服务。

    Router 层只处理 HTTP 请求和当前用户；
    本 Service 负责把请求转成可追踪的 BackgroundTask 记录，并投递 Celery。
    """

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
        """提交后台任务。

        任务先落库再投递 Celery，这样即使 Worker 异常，也能在数据库里看到失败原因。
        user_id 用于把任务归属到当前用户，后续查询和取消都要按用户隔离。
        """

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
        """取消尚未结束的后台任务。

        当前第一版取消是业务状态取消，主要防止用户继续看到任务处于可执行状态。
        已经 success / failed / cancelled 的终态任务不能再次取消。
        """

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
