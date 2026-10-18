"""
Database Session Management
============================
SQLAlchemy session factory for userdb and playdb.
"""
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from backend.config import USERDB_PATH, PLAYDB_PATH, DEBUG
from backend.database.models import Base


# =============================================================================
# USERDB (Persistent Data)
# =============================================================================

# Create engine for userdb (persistent)
userdb_engine = create_engine(
    f"sqlite:///{USERDB_PATH}",
    connect_args={"check_same_thread": False},
    echo=DEBUG,
)

# Session factory for userdb
UserDBSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=userdb_engine)


def get_userdb_session() -> Generator[Session, None, None]:
    """Get a userdb session (for persistent data like songs, playlists, queues)."""
    session = UserDBSessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_userdb() -> None:
    """Initialize userdb with all tables."""
    # Create all tables that belong to userdb
    # Note: We create all tables here since userdb and playdb share some models
    Base.metadata.create_all(bind=userdb_engine)
    print(f"[OK] UserDB initialized at {USERDB_PATH}")


# =============================================================================
# PLAYDB (Session Data)
# =============================================================================

# Create engine for playdb (session data, can be flushed)
playdb_engine = create_engine(
    f"sqlite:///{PLAYDB_PATH}",
    connect_args={"check_same_thread": False},
    echo=DEBUG,
)

# Session factory for playdb
PlayDBSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=playdb_engine)


def get_playdb_session() -> Generator[Session, None, None]:
    """Get a playdb session (for session data like playback state)."""
    session = PlayDBSessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_playdb() -> None:
    """Initialize playdb with playback state table."""
    # We only need the playback_state table for playdb
    # But we create all tables for now to avoid complexity
    Base.metadata.create_all(bind=playdb_engine)
    print(f"[OK] PlayDB initialized at {PLAYDB_PATH}")


def flush_playdb() -> None:
    """Clear all data from playdb (called on app restart)."""
    with playdb_engine.connect() as conn:
        # Delete all rows from playback_state
        conn.execute("DELETE FROM playback_state")
        conn.commit()
    print("[OK] PlayDB flushed")


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def reset_database(db_path: str) -> None:
    """
    Reset a database (delete all tables and recreate them).
    WARNING: This will delete all data!
    """
    import os
    from backend.database.models import Base
    
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"[DEL] Deleted database: {db_path}")
    
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)
    print(f"[OK] Recreated database: {db_path}")
