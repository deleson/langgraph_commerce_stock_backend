"""每日简报模式开关 API 测试。"""

from httpx import AsyncClient

from app.core.config import get_settings

API_PREFIX = "/api/v1"


async def test_get_and_update_daily_report_mode_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    get_response = await async_client.get(
        f"{API_PREFIX}/daily-reports/mode",
        headers=auth_headers,
    )

    assert get_response.status_code == 200
    initial_data = get_response.json()["data"]
    assert initial_data["daily_report_enabled"] is False
    assert initial_data["timezone"] == "Asia/Shanghai"
    settings = get_settings()
    expected_time = f"{settings.celery_beat_daily_report_hour:02d}:{settings.celery_beat_daily_report_minute:02d}"
    assert initial_data["scheduled_time"] == expected_time
    assert initial_data["effective_status"] == "disabled"
    assert initial_data["message"]

    enable_response = await async_client.patch(
        f"{API_PREFIX}/daily-reports/mode",
        json={"daily_report_enabled": True},
        headers=auth_headers,
    )

    assert enable_response.status_code == 200
    enabled_data = enable_response.json()["data"]
    assert enabled_data["daily_report_enabled"] is True
    assert enabled_data["timezone"] == "Asia/Shanghai"
    if enabled_data["scheduler_enabled"]:
        assert enabled_data["effective_status"] == "enabled"
    else:
        assert enabled_data["effective_status"] == "enabled_but_scheduler_off"
    assert enabled_data["message"]

    disable_response = await async_client.patch(
        f"{API_PREFIX}/daily-reports/mode",
        json={"daily_report_enabled": False},
        headers=auth_headers,
    )

    assert disable_response.status_code == 200
    disabled_data = disable_response.json()["data"]
    assert disabled_data["daily_report_enabled"] is False
    assert disabled_data["effective_status"] == "disabled"


async def test_daily_report_mode_requires_login(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get(f"{API_PREFIX}/daily-reports/mode")

    assert response.status_code == 401
