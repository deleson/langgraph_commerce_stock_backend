
"""数据库连接管理。

该文件集中创建 PostgreSQL 同步和异步连接，并提供 FastAPI 依赖可用的
Session 生成器。当前业务代码主要使用 AsyncSessionLocal 进行异步读写。

注意：
测试环境必须连接 `langgraph_commerce_test`，生产环境在 Docker Compose
中通过 `postgres` 服务名连接数据库，避免把测试数据写入生产库。
"""

from app.models import Base
from collections.abc import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


settings = get_settings()

# 同步 engine 主要保留给 Alembic、脚本或少量同步场景使用。
engine = create_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_pre_ping=settings.database_pool_pre_ping,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,

    pool_timeout=settings.database_pool_timeout_seconds,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)

# 异步 engine 是当前 FastAPI API、Service 和 pytest 夹具的主要数据库入口。
async_engine = create_async_engine(
    settings.database_async_url,
    echo=settings.database_echo,
    pool_pre_ping=settings.database_pool_pre_ping,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_timeout=settings.database_pool_timeout_seconds,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    autoflush=False,
    expire_on_commit=False,
)

def get_db_session() -> Generator[Session,None,None]:
    """提供同步数据库会话。

    当前主业务以异步会话为主，该函数主要用于兼容同步工具或脚本。
    """

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖使用的异步数据库会话生成器。

    Router 通过依赖注入拿到 AsyncSession，具体事务边界通常由 Service
    或调用方控制。
    """

    async with AsyncSessionLocal() as db:
        yield db
