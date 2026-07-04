"""后台任务 Repository。

本文件封装 background_tasks 表的数据访问，是 API 提交任务与 Celery Worker 执行任务之间的持久化连接点。
Repository 只负责任务记录和状态流转，不直接执行任务业务。
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_task import BackgroundTask
from app.schemas.background_task import (
    BackgroundTaskCreateRequest,
    BackgroundTaskListQuery,
)


class AsyncBackgroundTaskRepository:
    """异步后台任务数据访问对象。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_task(
        self,
        *,
        payload: BackgroundTaskCreateRequest,
        user_id: int | None = None,
    ) -> BackgroundTask:
        task = BackgroundTask(
            user_id=user_id,
            task_type=payload.task_type,
            status="pending",
            priority=payload.priority,
            source=payload.source,
            idempotency_key=payload.idempotency_key,
            payload=payload.payload,
            retry_count=0,
            max_retries=payload.max_retries,
            scheduled_for=payload.scheduled_for,
        )

        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def create_task_once(
        self,
        *,
        payload: BackgroundTaskCreateRequest,
        user_id: int | None = None,
    ) -> tuple[BackgroundTask, bool]:
        """按幂等键原子创建任务，并返回 ``(task, created)``。

        Beat 可能因重启或并发调度重复触发。数据库唯一索引配合
        ``ON CONFLICT DO NOTHING`` 保证同一业务键只会生成一条任务记录。
        """

        if payload.idempotency_key is None:
            return await self.create_task(payload=payload, user_id=user_id), True

        stmt = (
            pg_insert(BackgroundTask)
            .values(
                user_id=user_id,
                task_type=payload.task_type,
                status="pending",
                priority=payload.priority,
                source=payload.source,
                idempotency_key=payload.idempotency_key,
                payload=payload.payload,
                retry_count=0,
                max_retries=payload.max_retries,
                scheduled_for=payload.scheduled_for,
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
            .returning(BackgroundTask.id)
        )
        result = await self.db.execute(stmt)
        task_id = result.scalar_one_or_none()
        await self.db.commit()

        if task_id is not None:
            task = await self.get_task(task_id=task_id)
            if task is None:  # pragma: no cover - 数据库 RETURNING 的防御性分支
                raise RuntimeError("created background task could not be reloaded")
            return task, True

        existing = await self.get_task_by_idempotency_key(
            idempotency_key=payload.idempotency_key,
        )
        if existing is None:  # pragma: no cover - 唯一冲突后理论上必然存在
            raise RuntimeError("idempotent background task could not be loaded")
        return existing, False

    async def get_task_by_idempotency_key(
        self,
        *,
        idempotency_key: str,
    ) -> BackgroundTask | None:
        stmt = select(BackgroundTask).where(
            BackgroundTask.idempotency_key == idempotency_key
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_task(
        self,
        *,
        task_id: int,
    ) -> BackgroundTask | None:
        stmt = select(BackgroundTask).where(BackgroundTask.id == task_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_task_by_celery_task_id(
        self,
        *,
        celery_task_id: str,
    ) -> BackgroundTask | None:
        stmt = select(BackgroundTask).where(
            BackgroundTask.celery_task_id == celery_task_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        *,
        query: BackgroundTaskListQuery,
        user_id: int | None = None,
    ) -> list[BackgroundTask]:
        """分页查询后台任务列表。

        user_id 为空时通常用于系统内部查询；用户接口必须传入 user_id 做隔离。
        """

        stmt = select(BackgroundTask)

        if user_id is not None:
            stmt = stmt.where(BackgroundTask.user_id == user_id)

        if query.task_type is not None:
            stmt = stmt.where(BackgroundTask.task_type == query.task_type)

        if query.status is not None:
            stmt = stmt.where(BackgroundTask.status == query.status)

        stmt = (
            stmt.order_by(BackgroundTask.created_at.desc())
            .offset(query.offset)
            .limit(query.limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_tasks(
        self,
        *,
        query: BackgroundTaskListQuery,
        user_id: int | None = None,
    ) -> int:
        stmt = select(func.count(BackgroundTask.id))

        if user_id is not None:
            stmt = stmt.where(BackgroundTask.user_id == user_id)

        if query.task_type is not None:
            stmt = stmt.where(BackgroundTask.task_type == query.task_type)

        if query.status is not None:
            stmt = stmt.where(BackgroundTask.status == query.status)

        result = await self.db.execute(stmt)
        return int(result.scalar_one())

    async def mark_queued(
        self,
        *,
        task: BackgroundTask,
        celery_task_id: str | None = None,
    ) -> BackgroundTask:
        task.status = "queued"
        task.celery_task_id = celery_task_id
        task.queued_at = self._now()

        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def mark_running(
        self,
        *,
        task: BackgroundTask,
    ) -> BackgroundTask:
        task.status = "running"
        task.started_at = self._now()
        task.error_message = None

        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def mark_success(
        self,
        *,
        task: BackgroundTask,
        result: dict[str, Any] | None = None,
    ) -> BackgroundTask:
        """把任务标记为成功并保存执行结果。"""

        finished_at = self._now()

        task.status = "success"
        task.result = result
        task.error_message = None
        task.finished_at = finished_at
        task.duration_ms = self._calculate_duration_ms(
            started_at=task.started_at,
            finished_at=finished_at,
        )

        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def mark_failed(
        self,
        *,
        task: BackgroundTask,
        error_message: str,
        result: dict[str, Any] | None = None,
    ) -> BackgroundTask:
        """把任务标记为失败并记录错误信息。"""

        finished_at = self._now()

        task.status = "failed"
        task.result = result
        task.error_message = error_message
        task.finished_at = finished_at
        task.duration_ms = self._calculate_duration_ms(
            started_at=task.started_at,
            finished_at=finished_at,
        )

        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def mark_retrying(
        self,
        *,
        task: BackgroundTask,
        error_message: str | None = None,
    ) -> BackgroundTask:
        task.status = "retrying"
        task.retry_count += 1
        task.error_message = error_message

        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def mark_cancelled(
        self,
        *,
        task: BackgroundTask,
        error_message: str | None = None,
    ) -> BackgroundTask:
        finished_at = self._now()

        task.status = "cancelled"
        task.error_message = error_message
        task.finished_at = finished_at
        task.duration_ms = self._calculate_duration_ms(
            started_at=task.started_at,
            finished_at=finished_at,
        )

        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    def _calculate_duration_ms(
        self,
        *,
        started_at: datetime | None,
        finished_at: datetime,
    ) -> int | None:
        if started_at is None:
            return None

        return max(
            0,
            int((finished_at - started_at).total_seconds() * 1000),
        )

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)
