"""公共 pytest fixture 验证。

本文件确认 conftest.py 中的测试数据库、测试客户端、测试用户和认证头可以正常工作。
它是后续 API / Service 测试的地基。
"""

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def test_db_session_uses_test_database(db_session: AsyncSession) -> None:
    result = await db_session.execute(text("SELECT current_database()"))
    database_name = result.scalar_one()

    assert database_name == "langgraph_commerce_test"


async def test_async_client_can_request_openapi(async_client: AsyncClient) -> None:
    response = await async_client.get("/openapi.json")

    assert response.status_code == 200
    assert "paths" in response.json()


async def test_test_user_fixture_creates_active_user(test_user: User) -> None:
    assert test_user.id is not None
    assert test_user.email.endswith("@example.com")
    assert test_user.is_active is True
    assert test_user.status == "active"


async def test_auth_headers_fixture(auth_headers: dict[str, str]) -> None:
    assert "Authorization" in auth_headers
    assert auth_headers["Authorization"].startswith("Bearer ")
