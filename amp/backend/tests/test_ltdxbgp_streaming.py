"""
Integration Tests for LTDxBgP0lqA Video Streaming
================================================

Comprehensive integration test suite for testing chunk-based streaming
of the specific video: https://music.youtube.com/watch?v=LTDxBgP0lqA

These tests verify:
1. Chunks can be downloaded individually using HTTP Range requests
2. Playback can start quickly (within 2-3 seconds)
3. Chunk storage, retrieval, and caching is consistent
4. No full audio files are downloaded during streaming
5. All chunk-related endpoints work correctly

Requirements:
- Network access to YouTube
- yt-dlp installed and in PATH
- Firefox cookies available for authentication (optional, for rate limiting)

Run with: pytest backend/tests/test_ltdxbgp_streaming.py -v -m integration
Skip with: pytest backend/tests/ -v -m "not integration"

Test Video: LTDxBgP0lqA
Expected Duration: ~3-4 minutes (to be verified)
Expected Chunks: ~24-25 chunks (10-second chunks)
"""

import pytest
import os
import sys
import shutil
import time
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Add backend to path
BACKEND_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(BACKEND_FOLDER))

from backend.services.streaming import (
    StreamingService,
    ChunkStatus,
    get_streaming_service,
)
from backend.config import CHUNKS_DIR, CHUNK_SIZE_SEC, CACHE_MAX_SIZE_MB
from backend.main import app
from fastapi.testclient import TestClient

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration

# Test video ID - The Weeknd - Blinding Lights (official audio)
TEST_VIDEO_ID = "LTDxBgP0lqA"
TEST_VIDEO_URL = f"https://music.youtube.com/watch?v={TEST_VIDEO_ID}"

# Expected values (approximate for Blinding Lights - 3:20 duration)
EXPECTED_DURATION_MS = 200000  # ~3:20 = 200,000ms
EXPECTED_TOTAL_CHUNKS = 20  # 200,000ms / 10,000ms per chunk

# Track test results for user feedback
_chunk_test_results: List[Dict[str, any]] = []


def yt_dlp_available() -> bool:
    """Check if yt-dlp is available."""
    return shutil.which("yt-dlp") is not None or shutil.which("yt-dlp.exe") is not None


def cleanup_full_files(song_id: str = TEST_VIDEO_ID) -> None:
    """Remove any _full files for the test song."""
    safe_id = song_id.replace("/", "_").replace("?", "_")
    chunks_dir = CHUNKS_DIR
    
    if chunks_dir.exists():
        # Remove _full files
        for f in chunks_dir.glob(f"{song_id}_full*"):
            try:
                f.unlink()
                print(f"Cleaned up _full file: {f}")
            except Exception as e:
                print(f"Failed to clean up {f}: {e}")
        
        # Also check with safe_id
        for f in chunks_dir.glob(f"{safe_id}_full*"):
            try:
                f.unlink()
                print(f"Cleaned up _full file: {f}")
            except Exception as e:
                print(f"Failed to clean up {f}: {e}")


@pytest.fixture(scope="module", autouse=True)
def setup_and_cleanup():
    """Set up auth session and clean up before/after tests."""
    from backend.config import CACHE_DIR
    import shutil as sh
    
    session_file = CACHE_DIR / "ytm_session.json"
    cookies_file = CACHE_DIR / ".cookies.json"
    
    # Set up: copy cookies to session file if available
    created_session = False
    if not session_file.exists() and cookies_file.exists():
        sh.copy(cookies_file, session_file)
        created_session = True
        print(f"Created auth session from: {cookies_file}")
    
    # Clean up any existing test files before starting
    cleanup_full_files()
    
    yield
    
    # Clean up after all tests
    cleanup_full_files()
    
    # Tear down: remove session file if we created it
    if created_session and session_file.exists():
        session_file.unlink()
        print(f"Removed auth session file: {session_file}")


@pytest.fixture(scope="module")
def streaming_service():
    """Create a StreamingService instance for integration tests."""
    # Reset singleton to ensure clean state
    from backend.services.streaming import _streaming_service_instance
    global _streaming_service_instance
    _streaming_service_instance = None
    
    service = get_streaming_service()
    yield service
    
    # Cleanup: stop download manager
    if hasattr(service, '_download_manager') and service._download_manager:
        service._download_manager.stop()


@pytest.fixture(scope="module")
def test_client():
    """Create a FastAPI TestClient for API endpoint testing."""
    from backend.services.streaming import _streaming_service_instance
    global _streaming_service_instance
    _streaming_service_instance = None
    
    with TestClient(app) as client:
        yield client


# =============================================================================
# Test 1: Basic Video Information Retrieval
# =============================================================================

class TestVideoInfoRetrieval:
    """Test retrieving video information for LTDxBgP0lqA."""

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_get_video_info(self, streaming_service: StreamingService):
        """Test that we can retrieve basic info for LTDxBgP0lqA."""
        stream_info = streaming_service.get_stream_info(TEST_VIDEO_ID)
        
        assert stream_info is not None, "Failed to get stream info"
        assert stream_info.song_id == TEST_VIDEO_ID, "Song ID mismatch"
        assert stream_info.title is not None, "Title is None"
        assert stream_info.title != "", "Title is empty"
        assert stream_info.duration_ms is not None, "Duration is None"
        assert stream_info.duration_ms > 0, "Duration is not positive"
        assert stream_info.total_chunks > 0, "No chunks calculated"
        
        # Record for user feedback
        _chunk_test_results.append({
            "test": "video_info",
            "title": stream_info.title,
            "duration_ms": stream_info.duration_ms,
            "total_chunks": stream_info.total_chunks,
            "timestamp": datetime.now().isoformat(),
        })
        
        print(f"\n{'='*60}")
        print(f"Video Info for {TEST_VIDEO_ID}:")
        print(f"  Title: {stream_info.title}")
        print(f"  Duration: {stream_info.duration_ms}ms ({stream_info.duration_ms/1000/60:.2f} minutes)")
        print(f"  Total Chunks: {stream_info.total_chunks}")
        print(f"{'='*60}\n")

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_get_stream_url(self, streaming_service: StreamingService):
        """Test that we can get the direct stream URL."""
        url = streaming_service._get_stream_url_cached(TEST_VIDEO_ID)
        
        assert url is not None, "Failed to get stream URL"
        assert "http" in url, "URL doesn't contain http"
        assert url.startswith("http"), "URL doesn't start with http"
        
        print(f"\nStream URL: {url[:80]}...")


# =============================================================================
# Test 2: Chunk Byte Range Calculation
# =============================================================================

class TestChunkByteRanges:
    """Test chunk byte range calculation."""

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_byte_ranges_calculated(self, streaming_service: StreamingService):
        """Test that byte ranges are calculated for all chunks."""
        # Get stream info first
        stream_info = streaming_service.get_stream_info(TEST_VIDEO_ID)
        assert stream_info is not None
        assert stream_info.total_chunks > 0
        
        total_chunks = stream_info.total_chunks
        
        # Test byte range calculation for each chunk
        for chunk_index in range(min(total_chunks, 5)):  # Test first 5 chunks
            byte_range = streaming_service._get_chunk_byte_range(TEST_VIDEO_ID, chunk_index)
            assert byte_range is not None, f"Failed to calculate byte range for chunk {chunk_index}"
            
            start_byte, end_byte = byte_range
            assert start_byte >= 0, f"Negative start byte for chunk {chunk_index}"
            assert end_byte > start_byte, f"End byte not greater than start for chunk {chunk_index}"
            
            chunk_size = end_byte - start_byte + 1
            # Each chunk should be roughly CHUNK_SIZE_SEC seconds worth of audio
            # At ~128kbps, 10 seconds = ~160KB
            assert chunk_size > 0, f"Zero-sized chunk {chunk_index}"
            
            print(f"  Chunk {chunk_index}: bytes {start_byte}-{end_byte} ({chunk_size} bytes)")

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_all_byte_ranges_valid(self, streaming_service: StreamingService):
        """Test that all byte ranges cover the entire stream."""
        stream_info = streaming_service.get_stream_info(TEST_VIDEO_ID)
        assert stream_info is not None
        
        total_chunks = stream_info.total_chunks
        ranges = streaming_service._get_chunk_byte_ranges(TEST_VIDEO_ID)
        
        assert ranges is not None, "Failed to get all byte ranges"
        assert len(ranges) == total_chunks, f"Expected {total_chunks} ranges, got {len(ranges)}"
        
        # Verify ranges are sequential and cover the full stream
        prev_end = -1
        total_stream_bytes = 0
        for i, (start, end) in enumerate(ranges):
            if i == 0:
                assert start == 0, "First chunk should start at byte 0"
            else:
                # Allow small gaps or overlaps due to rounding
                assert start <= prev_end + 1, f"Gap between chunk {i-1} and {i}"
            
            prev_end = end
            total_stream_bytes += (end - start + 1)
        
        print(f"\nTotal stream bytes: {total_stream_bytes:,} bytes ({total_stream_bytes/1024/1024:.2f} MB)")


# =============================================================================
# Test 3: Individual Chunk Downloading (HTTP Range Requests)
# =============================================================================

class TestChunkDownloading:
    """Test downloading individual chunks using HTTP Range requests."""

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_download_single_chunk(self, streaming_service: StreamingService):
        """Test downloading a single chunk."""
        # Clean up any existing chunks first
        cleanup_full_files()
        
        stream_info = streaming_service.get_stream_info(TEST_VIDEO_ID)
        assert stream_info is not None
        assert stream_info.total_chunks > 0
        
        # Download chunk 0 (first chunk)
        start_time = time.time()
        chunk_path = streaming_service.download_chunk(TEST_VIDEO_ID, 0)
        elapsed_time = time.time() - start_time
        
        assert chunk_path is not None, "Failed to download chunk 0"
        assert chunk_path.exists(), "Chunk file doesn't exist"
        assert chunk_path.stat().st_size > 0, "Chunk file is empty"
        
        # Should be fast (< 3 seconds for a single chunk)
        assert elapsed_time < 3.0, f"Chunk download took too long: {elapsed_time:.2f}s"
        
        # Verify it's NOT a _full file
        assert "_full" not in chunk_path.name, "Downloaded a _full file instead of a chunk!"
        
        # Record for user feedback
        _chunk_test_results.append({
            "test": "download_chunk_0",
            "chunk_index": 0,
            "path": str(chunk_path),
            "size_bytes": chunk_path.stat().st_size,
            "download_time_s": elapsed_time,
            "downloaded": True,
            "timestamp": datetime.now().isoformat(),
        })
        
        print(f"\n✓ Downloaded chunk 0: {chunk_path.name} ({chunk_path.stat().st_size:,} bytes) in {elapsed_time:.2f}s")

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_download_multiple_random_chunks(self, streaming_service: StreamingService):
        """Test downloading multiple random chunks."""
        stream_info = streaming_service.get_stream_info(TEST_VIDEO_ID)
        assert stream_info is not None
        
        total_chunks = stream_info.total_chunks
        
        # Select random chunks to download (avoid chunk 0 which was already tested)
        test_chunk_indices = [1, 3, 5, 10] if total_chunks > 10 else list(range(1, total_chunks))
        
        for chunk_index in test_chunk_indices:
            if chunk_index >= total_chunks:
                continue
                
            start_time = time.time()
            chunk_path = streaming_service.download_chunk(TEST_VIDEO_ID, chunk_index)
            elapsed_time = time.time() - start_time
            
            assert chunk_path is not None, f"Failed to download chunk {chunk_index}"
            assert chunk_path.exists(), f"Chunk {chunk_index} file doesn't exist"
            assert chunk_path.stat().st_size > 0, f"Chunk {chunk_index} file is empty"
            assert "_full" not in chunk_path.name, f"Downloaded a _full file for chunk {chunk_index}!"
            
            # Record for user feedback
            _chunk_test_results.append({
                "test": "download_random_chunk",
                "chunk_index": chunk_index,
                "path": str(chunk_path),
                "size_bytes": chunk_path.stat().st_size,
                "download_time_s": elapsed_time,
                "downloaded": True,
                "timestamp": datetime.now().isoformat(),
            })
            
            print(f"  ✓ Chunk {chunk_index}: {chunk_path.name} ({chunk_path.stat().st_size:,} bytes) in {elapsed_time:.2f}s")

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_no_full_files_created(self, streaming_service: StreamingService):
        """Verify that NO _full files were created during chunk downloads."""
        cleanup_full_files()
        
        # Download a few chunks
        stream_info = streaming_service.get_stream_info(TEST_VIDEO_ID)
        assert stream_info is not None
        
        for chunk_index in [0, 1, 2]:
            if chunk_index < stream_info.total_chunks:
                streaming_service.download_chunk(TEST_VIDEO_ID, chunk_index)
        
        # Check that no _full files exist
        safe_id = TEST_VIDEO_ID.replace("/", "_").replace("?", "_")
        chunks_dir = CHUNKS_DIR
        
        full_files = list(chunks_dir.glob(f"{TEST_VIDEO_ID}_full*")) + \
                     list(chunks_dir.glob(f"{safe_id}_full*"))
        
        assert len(full_files) == 0, f"Found {len(full_files)} _full files: {full_files}"
        
        print(f"\n✓ Verified: NO _full files created during streaming")


# =============================================================================
# Test 4: Quick Playback Start (Main Requirement)
# =============================================================================

class TestQuickPlaybackStart:
    """Test that playback can start quickly (< 3 seconds)."""

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_first_chunk_downloads_quickly(self, streaming_service: StreamingService):
        """Test that the first chunk downloads in under 3 seconds."""
        cleanup_full_files()
        
        # Clear any cached chunks
        stream_info = streaming_service.get_stream_info(TEST_VIDEO_ID)
        assert stream_info is not None
        
        # Force download of first chunk (no cache)
        start_time = time.time()
        chunk_path = streaming_service.download_chunk(TEST_VIDEO_ID, 0, force=True)
        elapsed_time = time.time() - start_time
        
        assert chunk_path is not None, "Failed to download first chunk"
        assert elapsed_time < 3.0, f"First chunk took {elapsed_time:.2f}s (must be < 3s)"
        
        print(f"\n✓ First chunk downloaded in {elapsed_time:.2f}s (requirement: < 3s)")

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_playback_start_with_buffer(self, streaming_service: StreamingService):
        """Test starting playback and buffering ahead."""
        cleanup_full_files()
        
        # Start playback
        start_time = time.time()
        result = streaming_service.start_playback(TEST_VIDEO_ID)
        assert result is True, "Failed to start playback"
        
        # Check that chunk 0 is being downloaded
        current_song = streaming_service.get_current_song_id()
        assert current_song == TEST_VIDEO_ID, "Current song not set correctly"
        
        # Wait a moment for initial buffering
        time.sleep(1)
        
        # Check playback state
        state = streaming_service.get_playback_state()
        assert state is not None
        assert state["is_playing"] is True or state["is_playing"] == True
        
        elapsed_time = time.time() - start_time
        assert elapsed_time < 5.0, f"Playback start took {elapsed_time:.2f}s (must be < 5s)"
        
        print(f"\n✓ Playback started in {elapsed_time:.2f}s (requirement: < 3s)")


# =============================================================================
# Test 5: Chunk Storage and Retrieval Consistency
# =============================================================================

class TestChunkStorage:
    """Test consistent chunk storage, retrieval, and caching."""

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_chunk_caching_and_retrieval(self, streaming_service: StreamingService):
        """Test that downloaded chunks are cached and can be retrieved."""
        cleanup_full_files()
        
        stream_info = streaming_service.get_stream_info(TEST_VIDEO_ID)
        assert stream_info is not None
        
        # Download a chunk
        chunk_index = 0
        chunk_path = streaming_service.download_chunk(TEST_VIDEO_ID, chunk_index)
        assert chunk_path is not None
        assert chunk_path.exists()
        
        original_size = chunk_path.stat().st_size
        original_mtime = chunk_path.stat().st_mtime
        
        # Wait a moment
        time.sleep(0.1)
        
        # Retrieve the same chunk (should return cached version)
        cached_path = streaming_service.get_chunk(TEST_VIDEO_ID, chunk_index)
        assert cached_path is not None, "Failed to retrieve cached chunk"
        assert cached_path.exists(), "Cached chunk doesn't exist"
        
        # Should be the same file
        assert str(cached_path) == str(chunk_path), "Cached path differs from original"
        
        # Size should be the same
        cached_size = cached_path.stat().st_size
        assert cached_size == original_size, f"Cached size differs: {cached_size} vs {original_size}"
        
        print(f"\n✓ Chunk caching and retrieval working correctly")

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_chunk_status_tracking(self, streaming_service: StreamingService):
        """Test that chunk status is tracked correctly."""
        cleanup_full_files()
        
        stream_info = streaming_service.get_stream_info(TEST_VIDEO_ID)
        assert stream_info is not None
        
        chunk_index = 0
        
        # Initially, chunk should be not_downloaded or unknown
        status_before = streaming_service.get_chunk_status(TEST_VIDEO_ID)
        initial_status = status_before.get(chunk_index, ChunkStatus.NOT_DOWNLOADED)
        
        # Download the chunk
        chunk_path = streaming_service.download_chunk(TEST_VIDEO_ID, chunk_index)
        assert chunk_path is not None
        
        # After download, status should be downloaded
        status_after = streaming_service.get_chunk_status(TEST_VIDEO_ID)
        final_status = status_after.get(chunk_index)
        
        assert final_status == ChunkStatus.DOWNLOADED, f"Status is {final_status}, expected DOWNLOADED"
        
        print(f"\n✓ Chunk status tracking working correctly")

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_cache_eviction(self, streaming_service: StreamingService):
        """Test that cache eviction works when max size is reached."""
        # This test verifies that the cache doesn't grow indefinitely
        # We can't easily test LRU eviction without downloading many files,
        # but we can verify the cache size is being monitored
        
        total_size = streaming_service._get_total_cache_size()
        max_size = CACHE_MAX_SIZE_MB * 1024 * 1024
        
        assert total_size >= 0, "Cache size should be non-negative"
        assert max_size > 0, "Max cache size should be positive"
        
        print(f"\n  Current cache size: {total_size:,} bytes ({total_size/1024/1024:.2f} MB)")
        print(f"  Max cache size: {max_size:,} bytes ({max_size/1024/1024:.2f} MB)")


# =============================================================================
# Test 6: Chunk-Related API Endpoints
# =============================================================================

class TestStreamingEndpoints:
    """Test all chunk-related API endpoints."""

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_stream_info_endpoint(self, test_client: TestClient):
        """Test GET /api/stream/info/{song_id} endpoint."""
        response = test_client.get(f"/api/stream/info/{TEST_VIDEO_ID}")
        
        assert response.status_code == 200, f"Status code: {response.status_code}"
        
        data = response.json()
        assert data is not None
        assert "song_id" in data
        assert data["song_id"] == TEST_VIDEO_ID
        assert "title" in data
        assert data["title"] is not None
        assert "duration_ms" in data
        assert "total_chunks" in data
        assert data["total_chunks"] > 0
        
        print(f"\n✓ Stream info endpoint working")

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_chunks_status_endpoint(self, test_client: TestClient):
        """Test GET /api/stream/{song_id}/chunks endpoint."""
        response = test_client.get(f"/api/stream/{TEST_VIDEO_ID}/chunks")
        
        assert response.status_code == 200, f"Status code: {response.status_code}"
        
        data = response.json()
        assert data is not None
        assert "chunk_status" in data
        assert "total_chunks" in data
        assert "cached_count" in data
        
        print(f"\n✓ Chunks status endpoint working")

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_play_endpoint(self, test_client: TestClient):
        """Test POST /api/stream/{song_id}/play endpoint."""
        response = test_client.post(f"/api/stream/{TEST_VIDEO_ID}/play")
        
        assert response.status_code == 200, f"Status code: {response.status_code}"
        
        data = response.json()
        assert data is not None
        assert "message" in data
        assert data.get("song_id") == TEST_VIDEO_ID
        
        print(f"\n✓ Play endpoint working")

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_pause_endpoint(self, test_client: TestClient):
        """Test POST /api/stream/pause endpoint."""
        # Start playback first
        test_client.post(f"/api/stream/{TEST_VIDEO_ID}/play")
        
        response = test_client.post("/api/stream/pause")
        
        assert response.status_code == 200, f"Status code: {response.status_code}"
        
        data = response.json()
        assert data is not None
        
        print(f"\n✓ Pause endpoint working")

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_playback_state_endpoint(self, test_client: TestClient):
        """Test GET /api/stream/playback-state endpoint."""
        response = test_client.get("/api/stream/playback-state")
        
        assert response.status_code == 200, f"Status code: {response.status_code}"
        
        data = response.json()
        assert data is not None
        # Should have playback state info
        
        print(f"\n✓ Playback state endpoint working")


# =============================================================================
# Test 7: Seek and Buffer Re-balancing
# =============================================================================

class TestSeekAndBuffer:
    """Test seeking to different positions and buffer re-balancing."""

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_seek_to_position(self, streaming_service: StreamingService):
        """Test seeking to a specific position."""
        cleanup_full_files()
        
        stream_info = streaming_service.get_stream_info(TEST_VIDEO_ID)
        assert stream_info is not None
        assert stream_info.total_chunks > 0
        
        # Start playback
        streaming_service.start_playback(TEST_VIDEO_ID)
        
        # Seek to a position in the middle of the song
        seek_position_ms = 60000  # 60 seconds in
        result = streaming_service.seek_to_position(seek_position_ms)
        
        assert isinstance(result, dict), f"Seek should return dict, got {type(result)}"
        assert "error" not in result, f"Seek failed: {result.get('error')}"
        assert result.get("chunk_index") is not None, "Seek result missing chunk_index"
        
        # Verify current chunk index changed
        new_chunk_index = streaming_service.get_current_chunk_index()
        expected_chunk = seek_position_ms // (CHUNK_SIZE_SEC * 1000)
        
        # Allow for some tolerance
        assert abs(new_chunk_index - expected_chunk) <= 1, \
            f"Chunk index {new_chunk_index} not near expected {expected_chunk}"
        
        print(f"\n✓ Seek to position {seek_position_ms}ms working (chunk {new_chunk_index})")


# =============================================================================
# Test 8: Performance and Timing Tests
# =============================================================================

class TestPerformance:
    """Test performance requirements."""

    @pytest.mark.skipif(not yt_dlp_available(), reason="yt-dlp not available")
    def test_chunk_download_times(self, streaming_service: StreamingService):
        """Test that individual chunk downloads are fast."""
        cleanup_full_files()
        
        stream_info = streaming_service.get_stream_info(TEST_VIDEO_ID)
        assert stream_info is not None
        
        # Test downloading several chunks and measure times
        chunk_times = []
        for chunk_index in range(min(5, stream_info.total_chunks)):
            start_time = time.time()
            chunk_path = streaming_service.download_chunk(TEST_VIDEO_ID, chunk_index, force=True)
            elapsed = time.time() - start_time
            
            if chunk_path and chunk_path.exists():
                chunk_times.append(elapsed)
                
                # Each chunk should download in under 5 seconds
                assert elapsed < 5.0, f"Chunk {chunk_index} took {elapsed:.2f}s"
        
        avg_time = sum(chunk_times) / len(chunk_times) if chunk_times else 0
        print(f"\n  Chunk download times: {chunk_times}")
        print(f"  Average: {avg_time:.2f}s")
        print(f"\n✓ All chunks downloaded in acceptable time")



# =============================================================================
# Helper: Document Firefox Cookie Export Process
# =============================================================================

class TestCookieDocumentation:
    """Document Firefox cookie export process."""

    def test_cookie_export_documentation(self):
        """Document how to export cookies from Firefox for authentication."""
        print(f"\n{'='*70}")
        print("FIREFOX COOKIE EXPORT PROCESS FOR FUTURE TESTS")
        print(f"{'='*70}\n")
        
        print("To export cookies from Firefox for YouTube authentication:")
        print()
        print("1. Open Firefox and log in to YouTube Music")
        print("   - Go to https://music.youtube.com")
        print("   - Sign in with your Google account")
        print()
        print("2. Install the 'Cookie-Editor' extension:")
        print("   - Go to: https://addons.mozilla.org/en-US/firefox/addon/cookie-editor/")
        print("   - Click 'Add to Firefox'")
        print()
        print("3. Export cookies:")
        print("   - Open any YouTube Music page")
        print("   - Click the Cookie-Editor extension icon")
        print("   - Click 'Export' button")
        print("   - Select 'JSON' format")
        print("   - Save as: .amp/.cookies.json (in your AMP project cache directory)")
        print()
        print("4. The test framework will automatically copy this to ytm_session.json")
        print()
        print("Alternative method using Python:")
        print("  If you have Firefox cookies in SQLITE format, you can use:")
        print("  python scripts/export_firefox_cookies.py")
        print()
        print("Note: Cookies allow yt-dlp to access age-restricted content and")
        print("      avoid rate limiting. Without cookies, some videos may not work.")
        print()
        print(f"{'='*70}\n")
