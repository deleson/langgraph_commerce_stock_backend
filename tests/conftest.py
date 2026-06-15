"""pytest 全局测试夹具。

本文件是整个测试体系的入口，负责三件最重要的事情：
1. 强制测试环境读取 .env.test；
2. 校验数据库 URL 指向 langgraph_commerce_test，避免误写开发库或生产库；
3. 为 API / Service / Repository 测试提供数据库会话、测试客户端、测试用户和认证头。

注意：这里的清库逻辑只服务于测试库，不应在开发库或生产库上运行。
"""

import os
from collections.abc import AsyncGenerator, Callable
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("APP_ENV_FILE", ".env.test")

from app.api.deps import get_async_db
from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.main import app
from app.models.user import User
from app.schemas.auth import UserRegisterRequest
from app.services.auth_service import AsyncAuthService


@pytest.fixture(scope="session", autouse=True)
def ensure_test_environment() -> None:
    """在测试会话启动时确认当前一定是测试环境。

    这道保护很重要：后续 clean_database 会清空业务表。
    如果环境变量配置错误，本断言会尽早失败，避免误删非测试数据库数据。
    """

    settings = get_settings()

    assert settings.app_env == "test"
    assert "langgraph_commerce_test" in settings.database_url
    assert "langgraph_commerce_test" in settings.database_async_url


async def _truncate_database() -> None:
    """清空测试库业务表，并保留 alembic_version。

    alembic_version 记录测试库迁移版本，不能随每个测试一起删除；
    其他业务表会通过 TRUNCATE ... CASCADE 清理，保证测试之间互不污染。
    """

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                  AND tablename != 'alembic_version'
                """
            )
        )
        table_names = result.scalars().all()

        if not table_names:
            return

        quoted_table_names = ", ".join(f'"{table_name}"' for table_name in table_names)

        await session.execute(
            text(f"TRUNCATE TABLE {quoted_table_names} RESTART IDENTITY CASCADE")
        )
        await session.commit()


@pytest.fixture(autouse=True)
async def clean_database() -> AsyncGenerator[None, None]:
    """每个测试前后清理测试库。

    前置清理避免受到上一个测试影响；
    后置清理避免失败测试残留数据影响后续排查。
    """

    await _truncate_database()
    yield
    await _truncate_database()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """提供测试用 AsyncSession。

    测试结束时 rollback，配合 clean_database 保持测试库干净。
    """

    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """提供不启动真实 Uvicorn 的 FastAPI 测试客户端。

    ASGITransport 会直接调用 app，并覆盖 get_async_db，
    因此 API 测试可以在 pytest 进程内完成。
    """

    async def override_get_async_db() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSessionLocal() as session:
            yield session

    app.dependency_overrides[get_async_db] = override_get_async_db

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def unique_email() -> Callable[[str], str]:
    """生成唯一邮箱，避免唯一约束冲突。"""

    def _build_email(prefix: str = "user") -> str:
        return f"{prefix}_{uuid4().hex}@example.com"

    return _build_email


@pytest.fixture
async def test_user(
    db_session: AsyncSession,
    unique_email: Callable[[str], str],
) -> User:
    """创建当前测试用户。

    多数需要认证的 API 测试都会通过该 fixture 获得当前用户上下文。
    """

    payload = UserRegisterRequest(
        email=unique_email("test_user"),
        username=f"user_{uuid4().hex[:12]}",
        password="TestPassword123",
    )

    user = await AsyncAuthService(db_session).register_user(payload)
    await db_session.commit()
    await db_session.refresh(user)

    return user


@pytest.fixture
async def another_test_user(
    db_session: AsyncSession,
    unique_email: Callable[[str], str],
) -> User:
    """创建第二个测试用户，用于验证跨用户隔离。"""

    payload = UserRegisterRequest(
        email=unique_email("another_user"),
        username=f"user_{uuid4().hex[:12]}",
        password="TestPassword123",
    )

    user = await AsyncAuthService(db_session).register_user(payload)
    await db_session.commit()
    await db_session.refresh(user)

    return user


@pytest.fixture
async def access_token(
    db_session: AsyncSession,
    test_user: User,
) -> str:
    """为 test_user 签发 access token。"""

    token, _ = await AsyncAuthService(db_session).issue_token_pair(test_user)
    await db_session.commit()

    return token


@pytest.fixture
async def auth_headers(access_token: str) -> dict[str, str]:
    """构造 Authorization 请求头。"""

    return {"Authorization": f"Bearer {access_token}"}
