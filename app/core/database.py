from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session,sessionmaker

from app.core.config import get_settings
from app.models import Base

settings = get_settings()

engine = create_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_pre_ping=settings.database_pool_pre_ping,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db_session() -> Generator[Session,None,None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()