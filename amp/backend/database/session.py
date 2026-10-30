"""SQLAlchemy engine (WAL + busy_timeout) and session factory."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import settings
from backend.database.models import Base

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def _make_engine() -> Engine:
    engine = create_engine(
        settings.db_url,
        echo=settings.DEBUG,
        pool_pre_ping=True,
        connect_args={
            "timeout": 10,
            "check_same_thread": False,
        },
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    return engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _make_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionFactory


def init_db() -> None:
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=get_engine())


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager that always closes the session."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()
