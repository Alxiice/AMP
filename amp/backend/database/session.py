"""SQLAlchemy engine (WAL + busy_timeout) and session factory."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import settings
from backend.database.models import Base, Segment
from backend.utils.logger import get_logger

logger = get_logger("backend.database.session")

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
    """Create all tables if they don't exist.

    create_all never alters existing tables. The segments table is only a
    cache, so if it predates a column (layout_id, Phase 2) it is dropped and
    recreated; cache reconciliation then deletes the orphaned files.
    """
    engine = get_engine()
    insp = inspect(engine)
    if insp.has_table(Segment.__tablename__):
        existing = {c["name"] for c in insp.get_columns(Segment.__tablename__)}
        missing = set(Segment.__table__.columns.keys()) - existing
        if missing:
            logger.info("segments table lacks %s; recreating it (cache only)", sorted(missing))
            Segment.__table__.drop(bind=engine)
    Base.metadata.create_all(bind=engine)


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
