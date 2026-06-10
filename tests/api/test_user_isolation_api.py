from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.auth_service import AsyncAuthService


API_PREFIX = "/api/v1"


@pytest.fixture
async def another_auth_headers(
    db_session: AsyncSession,
    another_test_user: User,
) -> dict[str, str]:
    token, _ = await AsyncAuthService(db_session).issue_token_pair(another_test_user)
    await db_session.commit()

    return {"Authorization": f"Bearer {token}"}


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


async def _create_other_daily_report(
    async_client: AsyncClient,
    another_auth_headers: dict[str, str],
) -> int:
    response = await async_client.post(
        f"{API_PREFIX}/daily-reports/generate",
        json={
            "use_ai": False,
            "force_rebuild": True,
            "notify": False,
            "include_candidates": False,
            "include_user_profile": False,
            "include_relevant_memories": False,
        },
        headers=another_auth_headers,
    )

    assert response.status_code == 200
    return response.json()["data"]["report"]["id"]


async def _create_other_quant_alert_rule(
    async_client: AsyncClient,
    another_auth_headers: dict[str, str],
) -> int:
    response = await async_client.post(
        f"{API_PREFIX}/quant-alerts/rules",
        json={
            "name": "Other User AAPL Strategy Alert",
            "rule_type": "strategy_signal",
            "market": "US",
            "symbol": "AAPL",
            "severity": "warning",
            "cooldown_minutes": 0,
            "enabled_notification": False,
            "description": "other user rule",
            "rule_config": {},
        },
        headers=another_auth_headers,
    )

    assert response.status_code == 201
    return response.json()["data"]["id"]


async def _create_other_paper_trading_account(
    async_client: AsyncClient,
    another_auth_headers: dict[str, str],
) -> int:
    response = await async_client.post(
        f"{API_PREFIX}/paper-trading/accounts",
        json={
            "name": "Other User Paper Account",
            "initial_cash": "100000",
            "currency": "CNY",
        },
        headers=another_auth_headers,
    )

    assert response.status_code == 201
    return response.json()["data"]["id"]


async def _create_other_background_task(
    async_client: AsyncClient,
    another_auth_headers: dict[str, str],
) -> int:
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
        headers=another_auth_headers,
    )

    assert response.status_code == 202
    return response.json()["data"]["task_id"]


async def test_current_user_cannot_get_other_users_daily_report(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    another_auth_headers: dict[str, str],
) -> None:
    report_id = await _create_other_daily_report(
        async_client,
        another_auth_headers,
    )

    response = await async_client.get(
        f"{API_PREFIX}/daily-reports/{report_id}",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "daily report not found"


async def test_current_user_daily_report_list_excludes_other_users_reports(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    another_auth_headers: dict[str, str],
) -> None:
    await _create_other_daily_report(
        async_client,
        another_auth_headers,
    )

    response = await async_client.get(
        f"{API_PREFIX}/daily-reports",
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["total"] == 0
    assert data["items"] == []


async def test_current_user_cannot_access_other_users_quant_alert_rule(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    another_auth_headers: dict[str, str],
) -> None:
    rule_id = await _create_other_quant_alert_rule(
        async_client,
        another_auth_headers,
    )

    get_response = await async_client.get(
        f"{API_PREFIX}/quant-alerts/rules/{rule_id}",
        headers=auth_headers,
    )
    assert get_response.status_code == 404
    assert get_response.json()["message"] == "quant alert rule not found"

    update_response = await async_client.patch(
        f"{API_PREFIX}/quant-alerts/rules/{rule_id}",
        json={
            "name": "Should Not Update",
        },
        headers=auth_headers,
    )
    assert update_response.status_code == 404
    assert update_response.json()["message"] == "quant alert rule not found"

    deactivate_response = await async_client.post(
        f"{API_PREFIX}/quant-alerts/rules/{rule_id}/deactivate",
        headers=auth_headers,
    )
    assert deactivate_response.status_code == 404
    assert deactivate_response.json()["message"] == "quant alert rule not found"


async def test_current_user_quant_alert_rule_list_excludes_other_users_rules(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    another_auth_headers: dict[str, str],
) -> None:
    await _create_other_quant_alert_rule(
        async_client,
        another_auth_headers,
    )

    response = await async_client.get(
        f"{API_PREFIX}/quant-alerts/rules",
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["total"] == 0
    assert data["items"] == []


async def test_current_user_cannot_access_other_users_paper_trading_account(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    another_auth_headers: dict[str, str],
) -> None:
    account_id = await _create_other_paper_trading_account(
        async_client,
        another_auth_headers,
    )

    endpoints = [
        ("get", f"{API_PREFIX}/paper-trading/accounts/{account_id}", None),
        ("get", f"{API_PREFIX}/paper-trading/accounts/{account_id}/config", None),
        ("get", f"{API_PREFIX}/paper-trading/accounts/{account_id}/positions", None),
        ("get", f"{API_PREFIX}/paper-trading/accounts/{account_id}/orders", None),
        ("get", f"{API_PREFIX}/paper-trading/accounts/{account_id}/trades", None),
        ("get", f"{API_PREFIX}/paper-trading/accounts/{account_id}/equity", None),
        ("get", f"{API_PREFIX}/paper-trading/accounts/{account_id}/runs", None),
    ]

    for method, url, payload in endpoints:
        response = await async_client.request(
            method,
            url,
            json=payload,
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert response.json()["message"] == "paper trading account not found"

    update_response = await async_client.patch(
        f"{API_PREFIX}/paper-trading/accounts/{account_id}",
        json={
            "name": "Should Not Update",
        },
        headers=auth_headers,
    )
    assert update_response.status_code == 404
    assert update_response.json()["message"] == "paper trading account not found"

    update_config_response = await async_client.patch(
        f"{API_PREFIX}/paper-trading/accounts/{account_id}/config",
        json={
            "is_enabled": False,
        },
        headers=auth_headers,
    )
    assert update_config_response.status_code == 404
    assert update_config_response.json()["message"] == "paper trading account not found"

    tick_response = await async_client.post(
        f"{API_PREFIX}/paper-trading/accounts/{account_id}/tick",
        json={
            "force": True,
            "notify": False,
        },
        headers=auth_headers,
    )
    assert tick_response.status_code == 404
    assert tick_response.json()["message"] == "paper trading account not found"


async def test_current_user_paper_trading_account_list_excludes_other_users_accounts(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    another_auth_headers: dict[str, str],
) -> None:
    await _create_other_paper_trading_account(
        async_client,
        another_auth_headers,
    )

    response = await async_client.get(
        f"{API_PREFIX}/paper-trading/accounts",
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["total"] == 0
    assert data["items"] == []


async def test_current_user_cannot_access_other_users_background_task(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    another_auth_headers: dict[str, str],
    mock_celery_send_task: list[dict],
) -> None:
    task_id = await _create_other_background_task(
        async_client,
        another_auth_headers,
    )

    get_response = await async_client.get(
        f"{API_PREFIX}/background-tasks/{task_id}",
        headers=auth_headers,
    )
    assert get_response.status_code == 404
    assert get_response.json()["message"] == "后台任务不存在"

    cancel_response = await async_client.post(
        f"{API_PREFIX}/background-tasks/{task_id}/cancel",
        headers=auth_headers,
    )
    assert cancel_response.status_code == 404
    assert cancel_response.json()["message"] == "后台任务不存在"


async def test_current_user_background_task_list_excludes_other_users_tasks(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    another_auth_headers: dict[str, str],
    mock_celery_send_task: list[dict],
) -> None:
    await _create_other_background_task(
        async_client,
        another_auth_headers,
    )

    response = await async_client.get(
        f"{API_PREFIX}/background-tasks",
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert data["total"] == 0
    assert data["items"] == []
