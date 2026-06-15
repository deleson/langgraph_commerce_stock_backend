"""用户上下文 API 测试。

覆盖自选股、用户偏好和通知中心，重点验证当前用户只能访问自己的上下文数据。
"""

from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.notification import NotificationCreateRequest
from app.schemas.watchlist import WatchlistCreateRequest
from app.services.notification_service import AsyncNotificationService
from app.services.watchlist_service import AsyncWatchlistService


API_PREFIX = "/api/v1"


async def test_create_watchlist_item_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    payload = {
        "symbol": "aapl",
        "market": "US",
        "name": "Apple",
        "notes": "long term watch",
        "alert_enabled": True,
    }

    response = await async_client.post(
        f"{API_PREFIX}/watchlist",
        json=payload,
        headers=auth_headers,
    )

    assert response.status_code == 201

    body = response.json()
    assert body["code"] == 0
    assert body["data"]["symbol"] == "AAPL"
    assert body["data"]["market"] == "US"
    assert body["data"]["name"] == "Apple"
    assert body["data"]["notes"] == "long term watch"
    assert body["data"]["alert_enabled"] is True


async def test_list_watchlist_items_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    create_response = await async_client.post(
        f"{API_PREFIX}/watchlist",
        json={
            "symbol": "MSFT",
            "market": "US",
            "name": "Microsoft",
            "alert_enabled": False,
        },
        headers=auth_headers,
    )
    assert create_response.status_code == 201

    response = await async_client.get(
        f"{API_PREFIX}/watchlist",
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 0
    assert len(body["data"]) == 1
    assert body["data"][0]["symbol"] == "MSFT"


async def test_get_watchlist_item_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    create_response = await async_client.post(
        f"{API_PREFIX}/watchlist",
        json={
            "symbol": "TSLA",
            "market": "US",
            "name": "Tesla",
        },
        headers=auth_headers,
    )
    assert create_response.status_code == 201
    item_id = create_response.json()["data"]["id"]

    response = await async_client.get(
        f"{API_PREFIX}/watchlist/{item_id}",
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 0
    assert body["data"]["id"] == item_id
    assert body["data"]["symbol"] == "TSLA"


async def test_update_watchlist_item_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    create_response = await async_client.post(
        f"{API_PREFIX}/watchlist",
        json={
            "symbol": "NVDA",
            "market": "US",
            "name": "Nvidia",
        },
        headers=auth_headers,
    )
    assert create_response.status_code == 201
    item_id = create_response.json()["data"]["id"]

    response = await async_client.patch(
        f"{API_PREFIX}/watchlist/{item_id}",
        json={
            "name": "Nvidia Updated",
            "notes": "watch AI chip trend",
            "alert_enabled": True,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 0
    assert body["data"]["name"] == "Nvidia Updated"
    assert body["data"]["notes"] == "watch AI chip trend"
    assert body["data"]["alert_enabled"] is True


async def test_delete_watchlist_item_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    create_response = await async_client.post(
        f"{API_PREFIX}/watchlist",
        json={
            "symbol": "BABA",
            "market": "US",
            "name": "Alibaba",
        },
        headers=auth_headers,
    )
    assert create_response.status_code == 201
    item_id = create_response.json()["data"]["id"]

    delete_response = await async_client.delete(
        f"{API_PREFIX}/watchlist/{item_id}",
        headers=auth_headers,
    )

    assert delete_response.status_code == 200
    assert delete_response.json()["data"]["message"] == "watchlist item deleted"

    get_response = await async_client.get(
        f"{API_PREFIX}/watchlist/{item_id}",
        headers=auth_headers,
    )
    assert get_response.status_code == 404


async def test_create_duplicate_watchlist_item_returns_conflict(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    payload = {
        "symbol": "AAPL",
        "market": "US",
        "name": "Apple",
    }

    first_response = await async_client.post(
        f"{API_PREFIX}/watchlist",
        json=payload,
        headers=auth_headers,
    )
    second_response = await async_client.post(
        f"{API_PREFIX}/watchlist",
        json=payload,
        headers=auth_headers,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409

    body = second_response.json()
    assert body["code"] == 10009
    assert body["message"] == "watchlist item already exists"


async def test_user_cannot_access_other_users_watchlist_item(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    another_test_user: User,
    auth_headers: dict[str, str],
) -> None:
    item = await AsyncWatchlistService(db_session).create_watchlist_item(
        user=another_test_user,
        payload=WatchlistCreateRequest(
            symbol=f"T{uuid4().hex[:4]}",
            market="US",
            name="Other User Stock",
        ),
    )

    response = await async_client.get(
        f"{API_PREFIX}/watchlist/{item.id}",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "watchlist item not found"


async def test_get_my_preference_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.get(
        f"{API_PREFIX}/preferences/me",
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 0
    assert body["data"]["risk_preference"] == "balanced"
    assert body["data"]["timezone"] == "Asia/Shanghai"
    assert body["data"]["daily_report_enabled"] is False
    assert body["data"]["abnormal_alert_enabled"] is False
    assert body["data"]["default_watchlist_alert_enabled"] is False


async def test_update_my_preference_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.patch(
        f"{API_PREFIX}/preferences/me",
        json={
            "risk_preference": "aggressive",
            "timezone": "Asia/Shanghai",
            "daily_report_enabled": True,
            "abnormal_alert_enabled": True,
            "default_watchlist_alert_enabled": True,
        },
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 0
    assert body["data"]["risk_preference"] == "aggressive"
    assert body["data"]["timezone"] == "Asia/Shanghai"
    assert body["data"]["daily_report_enabled"] is True
    assert body["data"]["abnormal_alert_enabled"] is True
    assert body["data"]["default_watchlist_alert_enabled"] is True


async def test_watchlist_uses_default_alert_preference_when_alert_enabled_missing(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    preference_response = await async_client.patch(
        f"{API_PREFIX}/preferences/me",
        json={"default_watchlist_alert_enabled": True},
        headers=auth_headers,
    )
    assert preference_response.status_code == 200

    response = await async_client.post(
        f"{API_PREFIX}/watchlist",
        json={
            "symbol": "AMD",
            "market": "US",
            "name": "AMD",
        },
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["data"]["alert_enabled"] is True


async def test_list_notifications_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict[str, str],
) -> None:
    await AsyncNotificationService(db_session).create_notification(
        user=test_user,
        payload=NotificationCreateRequest(
            title="Test Notification",
            content="Notification content",
            notification_type="system",
        ),
    )

    response = await async_client.get(
        f"{API_PREFIX}/notifications",
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 0
    assert len(body["data"]) == 1
    assert body["data"][0]["title"] == "Test Notification"
    assert body["data"][0]["is_read"] is False


async def test_list_unread_notifications_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict[str, str],
) -> None:
    notification_service = AsyncNotificationService(db_session)

    first = await notification_service.create_notification(
        user=test_user,
        payload=NotificationCreateRequest(
            title="Unread Notification",
            content="Unread content",
            notification_type="system",
        ),
    )
    second = await notification_service.create_notification(
        user=test_user,
        payload=NotificationCreateRequest(
            title="Read Notification",
            content="Read content",
            notification_type="system",
        ),
    )

    await notification_service.mark_my_notification_as_read(
        user=test_user,
        notification_id=second.id,
    )

    response = await async_client.get(
        f"{API_PREFIX}/notifications",
        params={"unread_only": True},
        headers=auth_headers,
    )

    assert response.status_code == 200

    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == first.id
    assert data[0]["is_read"] is False


async def test_get_notification_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict[str, str],
) -> None:
    notification = await AsyncNotificationService(db_session).create_notification(
        user=test_user,
        payload=NotificationCreateRequest(
            title="Detail Notification",
            content="Detail content",
            notification_type="system",
        ),
    )

    response = await async_client.get(
        f"{API_PREFIX}/notifications/{notification.id}",
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 0
    assert body["data"]["id"] == notification.id
    assert body["data"]["title"] == "Detail Notification"


async def test_mark_notification_as_read_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict[str, str],
) -> None:
    notification = await AsyncNotificationService(db_session).create_notification(
        user=test_user,
        payload=NotificationCreateRequest(
            title="Read Me",
            content="Read me content",
            notification_type="system",
        ),
    )

    response = await async_client.patch(
        f"{API_PREFIX}/notifications/{notification.id}/read",
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["data"]["is_read"] is True
    assert body["data"]["read_at"] is not None


async def test_mark_all_notifications_as_read_success(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict[str, str],
) -> None:
    notification_service = AsyncNotificationService(db_session)

    await notification_service.create_notification(
        user=test_user,
        payload=NotificationCreateRequest(
            title="First",
            content="First content",
            notification_type="system",
        ),
    )
    await notification_service.create_notification(
        user=test_user,
        payload=NotificationCreateRequest(
            title="Second",
            content="Second content",
            notification_type="system",
        ),
    )

    response = await async_client.patch(
        f"{API_PREFIX}/notifications/read-all",
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 0
    assert body["data"]["updated_count"] == 2

    list_response = await async_client.get(
        f"{API_PREFIX}/notifications",
        params={"unread_only": True},
        headers=auth_headers,
    )
    assert list_response.status_code == 200
    assert list_response.json()["data"] == []


async def test_user_cannot_access_other_users_notification(
    async_client: AsyncClient,
    db_session: AsyncSession,
    another_test_user: User,
    auth_headers: dict[str, str],
) -> None:
    notification = await AsyncNotificationService(db_session).create_notification(
        user=another_test_user,
        payload=NotificationCreateRequest(
            title="Other User Notification",
            content="Other user content",
            notification_type="system",
        ),
    )

    response = await async_client.get(
        f"{API_PREFIX}/notifications/{notification.id}",
        headers=auth_headers,
    )

    assert response.status_code == 404
    assert response.json()["message"] == "notification not found"
