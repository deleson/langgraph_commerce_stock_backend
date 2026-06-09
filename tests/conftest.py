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
    settings = get_settings()

    assert settings.app_env == "test"
    assert "langgraph_commerce_test" in settings.database_url
    assert "langgraph_commerce_test" in settings.database_async_url


async def _truncate_database() -> None:
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
    await _truncate_database()
    yield
    await _truncate_database()


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
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
    def _build_email(prefix: str = "user") -> str:
        return f"{prefix}_{uuid4().hex}@example.com"

    return _build_email


@pytest.fixture
async def test_user(
    db_session: AsyncSession,
    unique_email: Callable[[str], str],
) -> User:
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
    token, _ = await AsyncAuthService(db_session).issue_token_pair(test_user)
    await db_session.commit()

    return token


@pytest.fixture
async def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}