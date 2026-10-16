"""
Pytest configuration and fixtures for AMP backend tests.
"""
import pytest
import os
import sys

# Set OAuth environment variables before any imports
os.environ.setdefault("YOUTUBE_CLIENT_ID", "test_client_id")
os.environ.setdefault("YOUTUBE_CLIENT_SECRET", "test_client_secret")
os.environ.setdefault("YOUTUBE_REDIRECT_URI", "http://localhost:8000/api/auth/callback")


@pytest.fixture(scope="session", autouse=True)
def ensure_oauth_config():
    """Ensure OAuth configuration is available for all tests."""
    # These are already set above, but this ensures they persist
    pass
