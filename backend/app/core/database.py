from collections.abc import Iterator
from functools import lru_cache

from pymysql.connections import Connection
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

from app.core.config import get_settings


def set_utc_session(connection: Connection, _record: ConnectionPoolEntry) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SET time_zone = '+00:00'")


def create_database_engine(database_url: str) -> Engine:
    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=1800,
        connect_args={"charset": "utf8mb4", "connect_timeout": 10},
        hide_parameters=True,
    )
    event.listen(engine, "connect", set_utc_session)
    return engine


@lru_cache
def get_engine() -> Engine:
    return create_database_engine(get_settings().database_url.get_secret_value())


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def SessionLocal() -> Session:
    return get_session_factory()()


def get_db() -> Iterator[Session]:
    """Services explicitly commit successful transactions; exceptions roll back on close."""
    with SessionLocal() as session:
        yield session
