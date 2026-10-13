#!/usr/bin/env python3
"""
Test Setup
==========
Verify that the project is set up correctly.
"""
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_imports():
    """Test that all modules can be imported."""
    # Test config
    from backend.config import settings, BASE_DIR, CACHE_DIR, CHUNKS_DIR
    assert settings is not None
    
    # Test database models
    from backend.database.models import Base, Song, Playlist, Queue, PlaybackState
    assert Base is not None
    assert Song is not None
    
    # Test database session
    from backend.database.session import get_userdb_session, get_playdb_session, init_userdb, init_playdb
    assert callable(get_userdb_session)
    assert callable(get_playdb_session)
    
    # Test utils
    from backend.utils.logger import get_logger, setup_logging
    assert callable(get_logger)
    assert callable(setup_logging)
    
    # Test API
    from backend.api.server import app
    assert app is not None
    
    from backend.api.endpoints import router
    assert router is not None


def test_database_initialization():
    """Test that databases can be initialized."""
    from backend.database.session import init_userdb, init_playdb
    from backend.config import USERDB_PATH, PLAYDB_PATH
    
    # Initialize databases
    init_userdb()
    init_playdb()
    
    # Check if files exist
    assert USERDB_PATH.exists()
    assert PLAYDB_PATH.exists()


def test_fastapi_app():
    """Test that FastAPI app can be created."""
    from fastapi.testclient import TestClient
    from backend.api.server import app
    
    client = TestClient(app)
    
    # Test health endpoint
    response = client.get("/api/health")
    assert response.status_code == 200
    assert "status" in response.json()
    assert response.json()["status"] == "ok"


def test_directory_structure():
    """Test that directory structure is correct."""
    from backend.config import BASE_DIR, CACHE_DIR, CHUNKS_DIR, LOGS_DIR
    
    # BASE_DIR points to the project root (AMP/)
    expected_dirs = [
        BASE_DIR / "backend" / "database",
        BASE_DIR / "backend" / "api",
        BASE_DIR / "backend" / "utils",
        BASE_DIR / "backend" / "tests",
        CACHE_DIR,
        CHUNKS_DIR,
        LOGS_DIR,
    ]
    
    for dir_path in expected_dirs:
        assert dir_path.exists(), f"Directory does not exist: {dir_path}"
