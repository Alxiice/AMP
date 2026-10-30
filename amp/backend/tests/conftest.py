"""Shared pytest fixtures: temp dirs, DB reset, singleton cleanup."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure the amp/ directory is on the path
_amp_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_amp_root))


@pytest.fixture()
def temp_dirs(tmp_path, monkeypatch):
    """Redirect all storage paths to a temp directory.

    Private path attributes go through configure_paths/restore_paths, never
    monkeypatch (pydantic private attrs don't survive monkeypatch.undo).
    """
    from backend.config import settings

    snapshot = settings.snapshot_paths()
    settings.configure_paths(data_dir=tmp_path / ".amp", db_file=tmp_path / "test.sqlite")
    monkeypatch.setattr(settings, "CACHE_MAX_SIZE_MB", 1)  # 1 MB for fast eviction tests

    # Reset DB engine so it uses the new path
    import backend.database.session as session_mod
    session_mod._engine = None
    session_mod._SessionFactory = None

    # Create tables
    session_mod.init_db()

    try:
        yield {
            "cache_dir": settings.cache_dir,
            "segments_dir": settings.segments_dir,
            "logs_dir": settings.logs_dir,
            "db_file": settings.db_file,
            "tmp_path": tmp_path,
        }
    finally:
        settings.restore_paths(snapshot)
        if session_mod._engine is not None:
            session_mod._engine.dispose()
        session_mod._engine = None
        session_mod._SessionFactory = None


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset all service singletons between tests."""
    yield
    try:
        from backend.services.auth import reset_auth_service
        reset_auth_service()
    except Exception:
        pass
    try:
        from backend.services.youtube import reset_youtube_service
        reset_youtube_service()
    except Exception:
        pass
    try:
        from backend.services.streaming import reset_streaming_service
        reset_streaming_service()
    except Exception:
        pass


@pytest.fixture()
def auth_token():
    return "test-token-12345"


@pytest.fixture()
def client(temp_dirs, auth_token, monkeypatch):
    """FastAPI TestClient with auth token configured."""
    from backend.config import settings
    monkeypatch.setattr(settings, "AUTH_TOKEN", auth_token)

    from backend.api.server import create_app
    from fastapi.testclient import TestClient

    app = create_app(auth_token=auth_token)
    with TestClient(app) as c:
        # TestClient sends Host: testserver by default — override to pass the Host check
        c.headers.update({"Host": "127.0.0.1:8000"})
        yield c


@pytest.fixture()
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}", "Host": "127.0.0.1:8000"}


@pytest.fixture()
def client_no_auth(temp_dirs, monkeypatch):
    """FastAPI TestClient with NO auth token — open mode."""
    from backend.config import settings
    monkeypatch.setattr(settings, "AUTH_TOKEN", None)

    from backend.api.server import create_app
    from fastapi.testclient import TestClient

    app = create_app(auth_token=None)
    with TestClient(app) as c:
        c.headers.update({"Host": "127.0.0.1:8000"})
        yield c


@pytest.fixture()
def no_auth_headers():
    """Headers for open-mode requests (Host only, no Authorization)."""
    return {"Host": "127.0.0.1:8000"}
