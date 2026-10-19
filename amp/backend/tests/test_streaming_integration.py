"""
Integration Tests for Real Chunk Downloading
=============================================
Tests that download real audio chunks from YouTube Music.

These tests require:
- Network access to YouTube
- yt-dlp installed and in PATH

Run with: pytest backend/tests/test_streaming_integration.py -v -m integration
Skip with: pytest backend/tests/ -v -m "not integration"
"""

import pytest
import os
import sys
import shutil
import time
from pathlib import Path

# Add backend to path
BACKEND_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(BACKEND_FOLDER))

from backend.services.streaming import (
    StreamingService,
    ChunkStatus,
    get_streaming_service,
)
from backend.config import CHUNKS_DIR, CHUNK_SIZE_SEC

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration

# Test song: Rick Astley - Never Gonna Give You Up (very stable, well-known video)
TEST_SONG_ID = "dQw4w9WgXcQ"
TEST_SONG_URL = f"https://www.youtube.com/watch?v={TEST_SONG_ID}"


def yt_dlp_available() -> bool:
    """Check if yt-dlp is available."""
    return shutil.which("yt-dlp") is not None or shutil.which("yt-dlp.exe") is not None


@pytest.fixture(scope="module")
def streaming_service():
    """Create a StreamingService instance for integration tests."""
    service = StreamingService()
    yield service
    # Cleanup: stop download manager
    if hasattr(service, '_download_manager'):
        service._download_manager.stop()


@pytest.fixture(scope="session", autouse=True)
def setup_auth_session():
    """Set up auth session for integration tests by copying cookies file.
    
    The auth service looks for ytm_session.json in the cache directory.
    We copy from .cookies.json (which has the headers format) if it exists.
    Clean up after all integration tests complete.
    """
    from backend.config import CACHE_DIR
    import shutil as sh
    
    session_file = CACHE_DIR / "ytm_session.json"
    cookies_file = CACHE_DIR / ".cookies.json"
    
    # Set up: copy cookies to session file if available
    created_session = False
    if not session_file.exists() and cookies_file.exists():
        sh.copy(cookies_file, session_file)
        created_session = True
    
    yield
    
    # Tear down: remove session file if we created it
    if created_session and session_file.exists():
        session_file.unlink()


@pytest.fixture(scope="module")
def cleanup_test_files():
    """Clean up test files before and after tests."""
    # Clean before
    safe_id = TEST_SONG_ID.replace("/", "_").replace("?", "_")
    chunks_dir = CHUNKS_DIR
    if chunks_dir.exists():
        for f in chunks_dir.glob(f"{TEST_SONG_ID}*"):
            try:
                f.unlink()
            except Exception:
                pass
        for f in chunks_dir.glob(f"{safe_id}*"):
            try:
                f.unlink()
            except Exception:
                pass
    yield
    # Clean after
    if chunks_dir.exists():
        for f in chunks_dir.glob(f"{TEST_SONG_ID}*"):
            try:
                f.unlink()
            except Exception:
                pass
        for f in chunks_dir.glob(f"{safe_id}*"):
            try:
                f.unlink()
            except Exception:
                pass


class TestYtDlpAvailability:
    """Verify that yt-dlp is available for integration tests."""

    def test_yt_dlp_installed(self):
        """Test that yt-dlp is installed and accessible."""
        assert yt_dlp_available(), "yt-dlp is not installed or not in PATH"

    def test_yt_dlp_version(self):
        """Test that yt-dlp can report its version."""
        import subprocess
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0


class TestStreamInfoRealSong:
    """Test getting stream info for a real song."""

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_get_stream_info_real_song(self, streaming_service):
        """Test getting stream info for a real YouTube song."""
        info = streaming_service.get_stream_info(TEST_SONG_ID)

        assert info is not None, "Failed to get stream info"
        assert info.song_id == TEST_SONG_ID
        assert info.title is not None
        assert len(info.title) > 0
        # Never Gonna Give You Up is about 3:33 = 213 seconds
        assert info.duration_ms is not None, "Duration should be available"
        assert info.duration_ms > 0
        assert info.total_chunks > 0, "Should have at least one chunk"
        # 213 seconds / 10 seconds per chunk = ~22 chunks
        assert info.total_chunks >= 20, f"Expected ~22 chunks, got {info.total_chunks}"

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_get_duration_real_song(self, streaming_service):
        """Test getting duration for a real song using yt-dlp."""
        duration_ms = streaming_service._get_duration_with_yt_dlp(TEST_SONG_ID)

        assert duration_ms is not None, "Failed to get duration"
        assert duration_ms > 0
        # Should be approximately 213 seconds (3:33)
        assert 200000 < duration_ms < 230000, f"Duration {duration_ms}ms out of expected range"


class TestChunkDownloadRealSong:
    """Test downloading real chunks from a YouTube song."""

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_download_chunk_0(self, streaming_service, cleanup_test_files):
        """Test downloading chunk 0 of a real song."""
        chunk_path = streaming_service.download_chunk(TEST_SONG_ID, 0)

        assert chunk_path is not None, "Failed to download chunk 0"
        assert chunk_path.exists(), f"Chunk file does not exist: {chunk_path}"
        assert chunk_path.stat().st_size > 0, "Chunk file is empty"

        # Verify chunk status was updated
        status = streaming_service.get_chunk_status(TEST_SONG_ID)
        assert 0 in status, "Chunk 0 not in status"
        assert status[0] == ChunkStatus.DOWNLOADED, f"Chunk 0 status is {status[0]}"

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_download_chunk_1(self, streaming_service, cleanup_test_files):
        """Test downloading chunk 1 of a real song."""
        # First download chunk 0 (needed for fallback)
        chunk_0 = streaming_service.download_chunk(TEST_SONG_ID, 0)
        assert chunk_0 is not None, "Failed to download chunk 0"

        # Now download chunk 1
        chunk_1 = streaming_service.download_chunk(TEST_SONG_ID, 1)

        assert chunk_1 is not None, "Failed to download chunk 1"
        assert chunk_1.exists(), f"Chunk file does not exist: {chunk_1}"
        assert chunk_1.stat().st_size > 0, "Chunk file is empty"

        # Verify chunk status
        status = streaming_service.get_chunk_status(TEST_SONG_ID, total_chunks=5)
        assert 1 in status, "Chunk 1 not in status"

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_download_multiple_chunks(self, streaming_service, cleanup_test_files):
        """Test downloading multiple chunks sequentially."""
        results = []
        for i in range(3):
            chunk_path = streaming_service.download_chunk(TEST_SONG_ID, i)
            results.append(chunk_path)
            assert chunk_path is not None, f"Failed to download chunk {i}"
            assert chunk_path.exists(), f"Chunk {i} file does not exist"
            assert chunk_path.stat().st_size > 0, f"Chunk {i} file is empty"

        # Verify all chunks have different paths
        paths = [str(p) for p in results]
        assert len(set(paths)) == len(paths), "Chunk paths should be unique"

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_chunk_cached_on_second_download(self, streaming_service, cleanup_test_files):
        """Test that downloading the same chunk twice returns the cached version."""
        # First download
        chunk_path_1 = streaming_service.download_chunk(TEST_SONG_ID, 0)
        assert chunk_path_1 is not None

        file_size_1 = chunk_path_1.stat().st_size
        mtime_1 = chunk_path_1.stat().st_mtime

        # Second download (should return cached)
        chunk_path_2 = streaming_service.download_chunk(TEST_SONG_ID, 0)
        assert chunk_path_2 is not None
        assert chunk_path_2 == chunk_path_1, "Should return same path for cached chunk"

        # File should not have been modified
        assert chunk_path_2.stat().st_size == file_size_1
        assert chunk_path_2.stat().st_mtime == mtime_1

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_get_chunk_returns_downloaded(self, streaming_service, cleanup_test_files):
        """Test that get_chunk returns the path for a downloaded chunk."""
        # Download chunk
        downloaded = streaming_service.download_chunk(TEST_SONG_ID, 0)
        assert downloaded is not None

        # Get chunk should return the same path
        retrieved = streaming_service.get_chunk(TEST_SONG_ID, 0)
        assert retrieved is not None, "get_chunk returned None for downloaded chunk"
        assert retrieved.exists()

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_chunk_status_after_downloads(self, streaming_service, cleanup_test_files):
        """Test that chunk status is correctly tracked after downloads."""
        # Download chunks 0 and 1
        streaming_service.download_chunk(TEST_SONG_ID, 0)
        streaming_service.download_chunk(TEST_SONG_ID, 1)

        # Get full status
        status_info = streaming_service.get_song_chunks_status(TEST_SONG_ID)

        assert status_info["total_chunks"] > 0
        assert status_info["cached_count"] >= 1, f"Expected >=1 cached, got {status_info['cached_count']}"
        assert "chunk_status" in status_info

        # Chunk 0 should be downloaded
        chunk_status = status_info["chunk_status"]
        assert chunk_status.get("0") == "downloaded" or chunk_status.get(0) == "downloaded", \
            f"Chunk 0 status: {chunk_status.get('0') or chunk_status.get(0)}"


class TestFullSongDownloadRealSong:
    """Test downloading the full song for direct playback."""

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_download_full_song(self, streaming_service, cleanup_test_files):
        """Test downloading the full song audio file."""
        song_path = streaming_service.download_full_song(TEST_SONG_ID)

        assert song_path is not None, "Failed to download full song"
        assert song_path.exists(), f"Full song file does not exist: {song_path}"
        assert song_path.stat().st_size > 0, "Full song file is empty"

        # Should be a reasonable size for a ~3.5 minute song (at least 1MB for opus)
        file_size = song_path.stat().st_size
        assert file_size > 500_000, f"Full song file too small: {file_size} bytes"

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_get_full_song_path_cached(self, streaming_service, cleanup_test_files):
        """Test that get_full_song_path returns the path for a downloaded song."""
        # Download full song
        downloaded = streaming_service.download_full_song(TEST_SONG_ID)
        assert downloaded is not None

        # Get path should return the same file
        retrieved = streaming_service.get_full_song_path(TEST_SONG_ID)
        assert retrieved is not None, "get_full_song_path returned None"
        assert retrieved.exists()
        assert retrieved == downloaded

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_full_song_cached_on_second_download(self, streaming_service, cleanup_test_files):
        """Test that downloading the full song twice returns the cached version."""
        # First download
        path_1 = streaming_service.download_full_song(TEST_SONG_ID)
        assert path_1 is not None
        size_1 = path_1.stat().st_size

        # Second download (should return cached)
        path_2 = streaming_service.download_full_song(TEST_SONG_ID)
        assert path_2 is not None
        assert path_2 == path_1, "Should return same path for cached full song"
        assert path_2.stat().st_size == size_1


class TestPlaybackWithRealSong:
    """Test playback control with a real song."""

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_start_playback_real_song(self, streaming_service, cleanup_test_files):
        """Test starting playback for a real song."""
        result = streaming_service.start_playback(TEST_SONG_ID)

        assert result is True, "Failed to start playback"
        assert streaming_service.get_current_song_id() == TEST_SONG_ID
        assert streaming_service.get_playback_state()["is_playing"] is True

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_pause_resume_stop_playback(self, streaming_service, cleanup_test_files):
        """Test pause, resume, and stop playback flow."""
        # Start playback
        streaming_service.start_playback(TEST_SONG_ID)
        assert streaming_service.get_playback_state()["is_playing"] is True

        # Pause
        streaming_service.pause_playback()
        assert streaming_service.get_playback_state()["is_playing"] is False

        # Resume
        streaming_service.resume_playback()
        assert streaming_service.get_playback_state()["is_playing"] is True

        # Stop
        streaming_service.stop_playback()
        assert streaming_service.get_current_song_id() is None
        assert streaming_service.get_playback_state()["is_playing"] is False

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_update_playback_position(self, streaming_service, cleanup_test_files):
        """Test updating playback position."""
        streaming_service.start_playback(TEST_SONG_ID)

        # Update position to 30 seconds (chunk 3 with 10s chunks)
        streaming_service.update_playback_position(30000)

        state = streaming_service.get_playback_state()
        assert state["current_time_ms"] == 30000
        assert streaming_service.get_current_chunk_index() == 3

        # Stop
        streaming_service.stop_playback()


class TestChunkDownloadViaAPI:
    """Test chunk downloading through the API endpoints."""

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_api_chunks_status(self, cleanup_test_files):
        """Test the /api/stream/{song_id}/chunks endpoint."""
        from fastapi.testclient import TestClient
        from backend.main import app

        client = TestClient(app)
        response = client.get(f"/api/stream/{TEST_SONG_ID}/chunks")

        assert response.status_code == 200
        data = response.json()
        assert "total_chunks" in data
        assert "chunk_status" in data
        assert "cached_count" in data
        assert "downloading_count" in data
        assert data["total_chunks"] > 0

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_api_stream_info(self, cleanup_test_files):
        """Test the /api/stream/info/{song_id} endpoint."""
        from fastapi.testclient import TestClient
        from backend.main import app

        client = TestClient(app)
        response = client.get(f"/api/stream/info/{TEST_SONG_ID}")

        assert response.status_code == 200
        data = response.json()
        assert data["song_id"] == TEST_SONG_ID
        assert data["title"] is not None
        assert data["duration_ms"] is not None
        assert data["total_chunks"] > 0

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_api_playback_state(self, cleanup_test_files):
        """Test the /api/stream/playback-state endpoint."""
        from fastapi.testclient import TestClient
        from backend.main import app

        client = TestClient(app)
        response = client.get("/api/stream/playback-state")

        assert response.status_code == 200
        data = response.json()
        assert "current_song_id" in data
        assert "is_playing" in data
        assert "current_time_ms" in data
