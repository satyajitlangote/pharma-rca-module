"""SQLAlchemy 2.x engine / session / declarative base.

The dialect reported by /api/health always comes from `engine.dialect.name`,
i.e. the database we are actually connected to (postgresql or sqlite).
"""
from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

_IS_SQLITE = settings.database_url.startswith("sqlite")

# check_same_thread is required for SQLite used across FastAPI's threadpool.
_connect_args = {"check_same_thread": False} if _IS_SQLITE else {}

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


if _IS_SQLITE:
    # SQLite does not enforce FK/ON DELETE CASCADE unless this pragma is on.
    @event.listens_for(Engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):  # pragma: no cover
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db():
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
