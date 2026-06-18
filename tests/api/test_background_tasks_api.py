"""后台任务 API 测试。

通过 mock Celery send_task 验证任务提交、查询、列表、取消、投递失败和用户隔离。
本文件不启动真实 Celery Worker。
"""

from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_task import BackgroundTask
from app.models.user import User


API_PREFIX = "/api/v1"


@pytest.fixture
def mock_celery_send_task(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict] = []

    def fake_send_task(name: str, args: list[int] | None = None):
        calls.append(
            {
                "name": name,
                "args": args or [],
            }
        )
        return SimpleNamespace(id=f"mock-celery-task-{len(calls)}")

    monkeypatch.setattr(
        "app.services.background_task_service.celery_app.send_task",
        fake_send_task,
    )

    return calls


@pytest.fixture
def mock_celery_send_task_failed(monkeypatch: pytest.MonkeyPatch):
    def fake_send_task(name: str, args: list[int] | None = None):
        raise RuntimeError("mock celery unavailable")

    monkeypatch.setattr(
        "app.services.background_task_service.celery_app.send_task",
        fake_send_task,
    )


async def _create_background_task_model(
    db_session: AsyncSession,
    *,
    user_id: int | None,
    task_type: str = "market_data_sync",
    status: str = "queued",
    celery_task_id: str | None = "manual-celery-task",
    payload: dict | None = None,
) -> BackgroundTask:
    task = BackgroundTask(
        user_id=user_id,
        task_type=task_type,
        status=status,
        priority="normal",
        source="api",
        payload=payload
        or {
            "symbol": "AAPL",
            "market": "US",
            "timeframe": "1d",
            "limit": 40,
            "adjust_type": "none",
            "source": "mock",
        },
        celery_task_id=celery_task_id,
        retry_count=0,
        max_retries=3,
    )

    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    return task


async def test_submit_background_task_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    mock_celery_send_task: list[dict],
) -> None:
    response = await async_client.post(
        f"{API_PREFIX}/background-tasks",
        json={
            "task_type": "market_data_sync",
            "payload": {
                "symbol": "AAPL",
                "market": "US",
                "timeframe": "1d",
                "limit": 40,
                "adjust_type": "none",
                "source": "mock",
            },
            "priority": "normal",
            "source": "api",
            "max_retries": 3,
        },
        headers=auth_headers,
    )

    assert response.status_code == 202

    body = response.json()
    data = body["data"]

    assert body["code"] == 0
    assert data["task_id"] is not None
    assert data["task_type"] == "market_data_sync"
    assert data["status"] == "queued"
    assert data["celery_task_id"] == "mock-celery-task-1"
    assert data["message"] == "后台任务已提交，正在等待 Worker 执行"

    assert mock_celery_send_task == [
        {
            "name": "background_tasks.dispatch_background_task",
            "args": [data["task_id"]],
        }
    ]


async def test_get_background_task_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    mock_celery_send_task: list[dict],
) -> None:
    submit_response = await async_client.post(
        f"{API_PREFIX}/background-tasks",
        json={
            "task_type": "market_data_sync",
            "payload": {
                "symbol": "AAPL",
                "market": "US",
                "timeframe": "1d",
                "limit": 40,
                "adjust_type": "none",
                "source": "mock",
            },
            "priority": "high",
            "source": "api",
            "max_retries": 2,
        },
        headers=auth_headers,
    )
    assert submit_response.status_code == 202
    task_id = submit_response.json()["data"]["task_id"]

    response = await async_client.get(
        f"{API_PREFIX}/background-tasks/{task_id}",
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["id"] == task_id
    assert data["task_type"] == "market_data_sync"
    assert data["status"] == "queued"
    assert data["priority"] == "high"
    assert data["source"] == "api"
    assert data["payload"]["symbol"] == "AAPL"
    assert data["celery_task_id"] == "mock-celery-task-1"
    assert data["retry_count"] == 0
    assert data["max_retries"] == 2
    assert data["queued_at"] is not None


async def test_list_background_tasks_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    mock_celery_send_task: list[dict],
) -> None:
    for symbol in ["AAPL", "TSLA"]:
        response = await async_client.post(
            f"{API_PREFIX}/background-tasks",
            json={
                "task_type": "market_data_sync",
                "payload": {
                    "symbol": symbol,
                    "market": "US",
                    "timeframe": "1d",
                    "limit": 40,
                    "adjust_type": "none",
                    "source": "mock",
                },
                "priority": "normal",
                "source": "api",
                "max_retries": 3,
            },
            headers=auth_headers,
        )
        assert response.status_code == 202

    response = await async_client.get(
        f"{API_PREFIX}/background-tasks",
        params={
            "task_type": "market_data_sync",
            "status": "queued",
            "limit": 10,
            "offset": 0,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["total"] == 2
    assert data["limit"] == 10
    assert data["offset"] == 0
    assert len(data["items"]) == 2
    assert {item["payload"]["symbol"] for item in data["items"]} == {"AAPL", "TSLA"}
    assert all(item["status"] == "queued" for item in data["items"])


async def test_cancel_background_task_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    mock_celery_send_task: list[dict],
) -> None:
    submit_response = await async_client.post(
        f"{API_PREFIX}/background-tasks",
        json={
            "task_type": "market_data_sync",
            "payload": {
                "symbol": "AAPL",
                "market": "US",
                "timeframe": "1d",
                "limit": 40,
                "adjust_type": "none",
                "source": "mock",
            },
            "priority": "normal",
            "source": "api",
            "max_retries": 3,
        },
        headers=auth_headers,
    )
    assert submit_response.status_code == 202
    task_id = submit_response.json()["data"]["task_id"]

    response = await async_client.post(
        f"{API_PREFIX}/background-tasks/{task_id}/cancel",
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["id"] == task_id
    assert data["status"] == "cancelled"
    assert data["error_message"] == "任务已被取消"
    assert data["finished_at"] is not None


async def test_cancel_finished_background_task_returns_400(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict[str, str],
) -> None:
    task = await _create_background_task_model(
        db_session,
        user_id=test_user.id,
        status="success",
        celery_task_id="finished-celery-task",
    )

    response = await async_client.post(
        f"{API_PREFIX}/background-tasks/{task.id}/cancel",
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert response.json()["message"] == "已结束的后台任务不能取消"


async def test_user_cannot_get_other_users_background_task(
    async_client: AsyncClient,
    db_session: AsyncSession,
    another_test_user: User,
    auth_headers: dict[str, str],
) -> None:
    task = await _create_background_task_model(
        db_session,
        user_id=another_test_user.id,
        status="queued",
        celery_task_id="other-user-celery-task",
    )

    response = await async_client.get(
        f"{API_PREFIX}/background-tasks/{task.id}",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "后台任务不存在"


async def test_user_cannot_cancel_other_users_background_task(
    async_client: AsyncClient,
    db_session: AsyncSession,
    another_test_user: User,
    auth_headers: dict[str, str],
) -> None:
    task = await _create_background_task_model(
        db_session,
        user_id=another_test_user.id,
        status="queued",
        celery_task_id="other-user-cancel-celery-task",
    )

    response = await async_client.post(
        f"{API_PREFIX}/background-tasks/{task.id}/cancel",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "后台任务不存在"


async def test_list_background_tasks_only_returns_current_user_tasks(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    another_test_user: User,
    auth_headers: dict[str, str],
) -> None:
    own_task = await _create_background_task_model(
        db_session,
        user_id=test_user.id,
        status="queued",
        celery_task_id="own-celery-task",
        payload={
            "symbol": "AAPL",
            "market": "US",
            "source": "mock",
        },
    )
    await _create_background_task_model(
        db_session,
        user_id=another_test_user.id,
        status="queued",
        celery_task_id="other-list-celery-task",
        payload={
            "symbol": "TSLA",
            "market": "US",
            "source": "mock",
        },
    )

    response = await async_client.get(
        f"{API_PREFIX}/background-tasks",
        params={
            "limit": 20,
            "offset": 0,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == own_task.id
    assert data["items"][0]["payload"]["symbol"] == "AAPL"


async def test_submit_background_task_celery_failure_returns_400_and_marks_failed(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict[str, str],
    mock_celery_send_task_failed: None,
) -> None:
    response = await async_client.post(
        f"{API_PREFIX}/background-tasks",
        json={
            "task_type": "market_data_sync",
            "payload": {
                "symbol": "AAPL",
                "market": "US",
                "timeframe": "1d",
                "limit": 40,
                "adjust_type": "none",
                "source": "mock",
            },
            "priority": "normal",
            "source": "api",
            "max_retries": 3,
        },
        headers=auth_headers,
    )

    assert response.status_code == 400
    assert response.json()["message"] == "后台任务投递失败，请确认 Redis 和 Celery Worker 配置是否可用"

    from sqlalchemy import select

    result = await db_session.execute(
        select(BackgroundTask)
        .where(BackgroundTask.user_id == test_user.id)
        .where(BackgroundTask.task_type == "market_data_sync")
    )
    task = result.scalar_one()

    assert task.status == "failed"
    assert task.error_message == "mock celery unavailable"
    assert task.result == {
        "status": "failed",
        "reason": "celery_submit_failed",
    }


async def test_submit_background_task_invalid_type_returns_422(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.post(
        f"{API_PREFIX}/background-tasks",
        json={
            "task_type": "unknown_task",
            "payload": {},
            "priority": "normal",
            "source": "api",
            "max_retries": 3,
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


async def test_submit_background_task_invalid_payload_type_returns_422(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.post(
        f"{API_PREFIX}/background-tasks",
        json={
            "task_type": "market_data_sync",
            "payload": "not-object",
            "priority": "normal",
            "source": "api",
            "max_retries": 3,
        },
        headers=auth_headers,
    )

    assert response.status_code == 422


async def test_submit_watchlist_candle_sync_background_task_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    mock_celery_send_task: list[dict],
) -> None:
    response = await async_client.post(
        f"{API_PREFIX}/background-tasks",
        json={
            "task_type": "watchlist_candle_sync",
            "payload": {
                "market": "CN",
                "timeframe": "1d",
                "limit": 120,
                "adjust_type": "none",
                "source": "mock",
                "fallback_sources": ["mock"],
                "max_symbols": 300,
                "batch_size": 50,
                "stale_after_days": 3,
            },
            "priority": "normal",
            "source": "api",
            "max_retries": 2,
        },
        headers=auth_headers,
    )

    assert response.status_code == 202

    data = response.json()["data"]
    assert data["task_type"] == "watchlist_candle_sync"
    assert data["status"] == "queued"
    assert mock_celery_send_task[-1] == {
        "name": "background_tasks.dispatch_background_task",
        "args": [data["task_id"]],
    }
