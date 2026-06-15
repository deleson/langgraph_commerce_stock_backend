"""认证与当前用户 API 测试。

覆盖注册、登录、刷新 token、退出登录、当前用户查询和资料更新。
本文件不调用真实 LLM，也不依赖真实行情源。
"""

from collections.abc import Callable
from uuid import uuid4

from httpx import AsyncClient

from app.models.user import User


API_PREFIX = "/api/v1"


def _build_register_payload(
    unique_email: Callable[[str], str],
    *,
    prefix: str = "auth_user",
    password: str = "TestPassword123",
) -> dict[str, str]:
    return {
        "email": unique_email(prefix),
        "username": f"{prefix}_{uuid4().hex[:12]}",
        "password": password,
    }


async def test_register_user_success(
    async_client: AsyncClient,
    unique_email: Callable[[str], str],
) -> None:
    payload = _build_register_payload(unique_email)

    response = await async_client.post(
        f"{API_PREFIX}/auth/register",
        json=payload,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 0
    assert body["message"] == "success"
    assert body["data"]["email"] == payload["email"].lower()
    assert body["data"]["username"] == payload["username"]
    assert body["data"]["is_active"] is True
    assert body["data"]["is_superuser"] is False
    assert body["data"]["status"] == "active"
    assert "hashed_password" not in body["data"]


async def test_register_user_with_duplicate_email_returns_conflict(
    async_client: AsyncClient,
    unique_email: Callable[[str], str],
) -> None:
    email = unique_email("duplicate_email")
    first_payload = {
        "email": email,
        "username": f"user_{uuid4().hex[:12]}",
        "password": "TestPassword123",
    }
    second_payload = {
        "email": email,
        "username": f"user_{uuid4().hex[:12]}",
        "password": "TestPassword123",
    }

    first_response = await async_client.post(
        f"{API_PREFIX}/auth/register",
        json=first_payload,
    )
    second_response = await async_client.post(
        f"{API_PREFIX}/auth/register",
        json=second_payload,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 409

    body = second_response.json()
    assert body["code"] == 10009
    assert body["message"] == "email already exists"


async def test_login_user_success(
    async_client: AsyncClient,
    unique_email: Callable[[str], str],
) -> None:
    password = "TestPassword123"
    payload = _build_register_payload(
        unique_email,
        prefix="login_user",
        password=password,
    )

    register_response = await async_client.post(
        f"{API_PREFIX}/auth/register",
        json=payload,
    )
    assert register_response.status_code == 200

    login_response = await async_client.post(
        f"{API_PREFIX}/auth/login",
        json={
            "email": payload["email"],
            "password": password,
        },
    )

    assert login_response.status_code == 200

    body = login_response.json()
    assert body["code"] == 0
    assert body["data"]["token_type"] == "bearer"
    assert body["data"]["access_token"]
    assert body["data"]["refresh_token"]


async def test_login_user_with_wrong_password_returns_unauthorized(
    async_client: AsyncClient,
    unique_email: Callable[[str], str],
) -> None:
    payload = _build_register_payload(
        unique_email,
        prefix="wrong_password_user",
        password="TestPassword123",
    )

    register_response = await async_client.post(
        f"{API_PREFIX}/auth/register",
        json=payload,
    )
    assert register_response.status_code == 200

    login_response = await async_client.post(
        f"{API_PREFIX}/auth/login",
        json={
            "email": payload["email"],
            "password": "WrongPassword123",
        },
    )

    assert login_response.status_code == 401

    body = login_response.json()
    assert body["code"] == 10010
    assert body["message"] == "invalid email or password"


async def test_refresh_token_success(
    async_client: AsyncClient,
    unique_email: Callable[[str], str],
) -> None:
    password = "TestPassword123"
    payload = _build_register_payload(
        unique_email,
        prefix="refresh_user",
        password=password,
    )

    register_response = await async_client.post(
        f"{API_PREFIX}/auth/register",
        json=payload,
    )
    assert register_response.status_code == 200

    login_response = await async_client.post(
        f"{API_PREFIX}/auth/login",
        json={
            "email": payload["email"],
            "password": password,
        },
    )
    assert login_response.status_code == 200

    refresh_token = login_response.json()["data"]["refresh_token"]

    refresh_response = await async_client.post(
        f"{API_PREFIX}/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert refresh_response.status_code == 200

    body = refresh_response.json()
    assert body["code"] == 0
    assert body["data"]["token_type"] == "bearer"
    assert body["data"]["access_token"]
    assert body["data"]["refresh_token"]


async def test_logout_user_success(
    async_client: AsyncClient,
    unique_email: Callable[[str], str],
) -> None:
    password = "TestPassword123"
    payload = _build_register_payload(
        unique_email,
        prefix="logout_user",
        password=password,
    )

    register_response = await async_client.post(
        f"{API_PREFIX}/auth/register",
        json=payload,
    )
    assert register_response.status_code == 200

    login_response = await async_client.post(
        f"{API_PREFIX}/auth/login",
        json={
            "email": payload["email"],
            "password": password,
        },
    )
    assert login_response.status_code == 200

    token_data = login_response.json()["data"]

    logout_response = await async_client.post(
        f"{API_PREFIX}/auth/logout",
        json={"refresh_token": token_data["refresh_token"]},
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
    )

    assert logout_response.status_code == 200

    body = logout_response.json()
    assert body["code"] == 0
    assert body["data"]["message"] == "logout success"


async def test_get_current_user_without_token_returns_unauthorized(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get(f"{API_PREFIX}/users/me")

    assert response.status_code == 401


async def test_get_current_user_success(
    async_client: AsyncClient,
    test_user: User,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.get(
        f"{API_PREFIX}/users/me",
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 0
    assert body["data"]["id"] == test_user.id
    assert body["data"]["email"] == test_user.email
    assert body["data"]["username"] == test_user.username
    assert body["data"]["status"] == "active"


async def test_update_current_user_username_success(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    new_username = f"updated_{uuid4().hex[:12]}"

    response = await async_client.patch(
        f"{API_PREFIX}/users/me",
        json={"username": new_username},
        headers=auth_headers,
    )

    assert response.status_code == 200

    body = response.json()
    assert body["code"] == 0
    assert body["data"]["username"] == new_username


async def test_update_current_user_with_existing_username_returns_conflict(
    async_client: AsyncClient,
    another_test_user: User,
    auth_headers: dict[str, str],
) -> None:
    response = await async_client.patch(
        f"{API_PREFIX}/users/me",
        json={"username": another_test_user.username},
        headers=auth_headers,
    )

    assert response.status_code == 409

    body = response.json()
    assert body["code"] == 10009
    assert body["message"] == "username already exists"
