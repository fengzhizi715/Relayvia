from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine():
    settings = get_settings()
    if settings.database_url.startswith("mysql"):
        return create_engine(
            settings.database_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 2},
            pool_size=settings.database_pool_size,
        )
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)


def get_db():
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
