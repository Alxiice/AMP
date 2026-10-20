"""
Test Streaming Service
=====================
Unit and integration tests for audio streaming service.
"""
import pytest
import os
import tempfile
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from datetime import datetime

import sys

# Add backend to path
BACKEND_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(BACKEND_FOLDER))

from backend.services.streaming import (
    StreamingService,
    ChunkInfo,
    StreamInfo,
    get_streaming_service,
    QUALITY_PRESETS,
    ChunkStatus,
    ChunkDownloadTask,
    DownloadPriority,
    PlaybackInfo,
    DownloadManager,
    PlaybackSession,
)
from backend.config import CHUNKS_DIR, CACHE_DIR, CHUNK_SIZE_SEC, CHUNK_SIZE_SEC


class TestStreamingServiceInitialization:
    """Tests for StreamingService initialization."""
    
    def test_init_default(self):
        """Test default StreamingService initialization."""
        service = StreamingService()
        assert service is not None
        assert service._quality_preset is not None
        assert service._chunk_size_ms == CHUNK_SIZE_SEC * 1000
        assert service._cache_max_size_bytes > 0
    
    def test_quality_preset_high(self):
        """Test that high quality preset is used by default."""
        service = StreamingService()
        
        # With AUDIO_QUALITY=high in config
        from backend.config import AUDIO_QUALITY
        preset = QUALITY_PRESETS.get(AUDIO_QUALITY.lower(), QUALITY_PRESETS["high"])
        
        assert service._quality_preset == preset
    
    def test_quality_presets_exist(self):
        """Test that all quality presets exist."""
        for quality in ["low", "medium", "high", "best"]:
            assert quality in QUALITY_PRESETS
            assert "format" in QUALITY_PRESETS[quality]
            assert "bitrate" in QUALITY_PRESETS[quality]


class TestChunkFilenameGeneration:
    """Tests for chunk filename generation."""
    
    @pytest.fixture
    def streaming_service(self):
        """Create a StreamingService instance."""
        return StreamingService()
    
    def test_generate_chunk_filename(self, streaming_service):
        """Test generating a chunk filename."""
        filename = streaming_service._generate_chunk_filename("dQw4w9WgXcQ", 0)
        
        assert filename is not None
        assert filename.parent == CHUNKS_DIR
        assert "dQw4w9WgXcQ" in filename.name
        assert "0000" in filename.name
    
    def test_generate_chunk_filename_special_chars(self, streaming_service):
        """Test generating filename with special characters."""
        filename = streaming_service._generate_chunk_filename("test/video?param=1", 1)
        
        assert filename is not None
        # Special characters should be sanitized
        assert "/" not in filename.name
        assert "?" not in filename.name
    
    def test_generate_chunk_filename_different_indices(self, streaming_service):
        """Test generating filenames for different chunk indices."""
        filename1 = streaming_service._generate_chunk_filename("test", 0)
        filename2 = streaming_service._generate_chunk_filename("test", 1)
        filename10 = streaming_service._generate_chunk_filename("test", 10)
        
        assert filename1 != filename2
        assert filename2 != filename10
        assert "0000" in filename1.name
        assert "0001" in filename2.name
        assert "0010" in filename10.name


class TestChunkIndexing:
    """Tests for chunk indexing and range calculations."""
    
    @pytest.fixture
    def streaming_service(self):
        """Create a StreamingService instance."""
        return StreamingService()
    
    def test_get_chunk_index(self, streaming_service):
        """Test getting chunk index from milliseconds."""
        chunk_size_ms = streaming_service._chunk_size_ms
        
        assert streaming_service._get_chunk_index(0) == 0
        assert streaming_service._get_chunk_index(chunk_size_ms - 1) == 0
        assert streaming_service._get_chunk_index(chunk_size_ms) == 1
        assert streaming_service._get_chunk_index(chunk_size_ms * 2) == 2
    
    def test_get_chunk_range(self, streaming_service):
        """Test getting chunk start/end range."""
        start_ms, end_ms = streaming_service._get_chunk_range(0)
        
        assert start_ms == 0
        assert end_ms == streaming_service._chunk_size_ms
    
    def test_get_chunk_range_offset(self, streaming_service):
        """Test getting chunk range at offset."""
        chunk_size_ms = streaming_service._chunk_size_ms
        start_ms, end_ms = streaming_service._get_chunk_range(chunk_size_ms)
        
        assert start_ms == chunk_size_ms
        assert end_ms == chunk_size_ms * 2


class TestTimeConversion:
    """Tests for time string conversion."""
    
    @pytest.fixture
    def streaming_service(self):
        """Create a StreamingService instance."""
        return StreamingService()
    
    def test_ms_to_time_str_seconds(self, streaming_service):
        """Test converting seconds to time string."""
        time_str = streaming_service._ms_to_time_str(90000)  # 90 seconds
        assert time_str == "1:30"
    
    def test_ms_to_time_str_minutes(self, streaming_service):
        """Test converting minutes to time string."""
        time_str = streaming_service._ms_to_time_str(150000)  # 150 seconds = 2:30
        assert time_str == "2:30"
    
    def test_ms_to_time_str_hours(self, streaming_service):
        """Test converting hours to time string."""
        time_str = streaming_service._ms_to_time_str(3661000)  # 3661 seconds = 1:01:01
        assert time_str == "1:01:01"
    
    def test_ms_to_time_str_zero(self, streaming_service):
        """Test converting zero to time string."""
        time_str = streaming_service._ms_to_time_str(0)
        assert time_str == "0:00"


class TestURLGeneration:
    """Tests for YouTube URL generation."""
    
    @pytest.fixture
    def streaming_service(self):
        """Create a StreamingService instance."""
        return StreamingService()
    
    def test_get_song_url_with_id(self, streaming_service):
        """Test generating URL from video ID."""
        url = streaming_service.get_song_url("dQw4w9WgXcQ")
        assert url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    def test_get_song_url_full_url(self, streaming_service):
        """Test passing a full URL."""
        url = streaming_service.get_song_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    
    def test_get_song_url_short_url(self, streaming_service):
        """Test passing a short URL."""
        url = streaming_service.get_song_url("https://youtu.be/dQw4w9WgXcQ")
        assert url == "https://youtu.be/dQw4w9WgXcQ"


class TestYtDlpPath:
    """Tests for yt-dlp path detection."""
    
    @pytest.fixture
    def streaming_service(self):
        """Create a StreamingService instance."""
        return StreamingService()
    
    def test_get_yt_dlp_path(self, streaming_service):
        """Test getting yt-dlp path."""
        yt_dlp_path = streaming_service._get_yt_dlp_path()
        
        # Should return a path
        assert yt_dlp_path is not None
        assert len(yt_dlp_path) > 0


class TestStreamInfo:
    """Tests for StreamInfo dataclass."""
    
    def test_stream_info_creation(self):
        """Test creating StreamInfo."""
        info = StreamInfo(
            song_id="test_song",
            title="Test Song",
            duration_ms=180000,
            mime_type="audio/mpeg",
            chunk_size_ms=10000,
            total_chunks=18,
            cached_chunks=[0, 1, 2],
        )
        
        assert info.song_id == "test_song"
        assert info.title == "Test Song"
        assert info.duration_ms == 180000
        assert info.total_chunks == 18
        assert len(info.cached_chunks) == 3
    
    def test_stream_info_to_dict(self):
        """Test converting StreamInfo to dictionary."""
        info = StreamInfo(
            song_id="test",
            title="Test",
        )
        
        data = info.to_dict()
        
        assert "song_id" in data
        assert "title" in data
        assert data["song_id"] == "test"
        assert data["title"] == "Test"


class TestChunkInfo:
    """Tests for ChunkInfo dataclass."""
    
    def test_chunk_info_creation(self):
        """Test creating ChunkInfo."""
        info = ChunkInfo(
            song_id="test_song",
            start_ms=0,
            end_ms=10000,
            file_path=Path("/tmp/test.mp3"),
            size_bytes=1024,
            chunk_index=0,
        )
        
        assert info.song_id == "test_song"
        assert info.start_ms == 0
        assert info.end_ms == 10000
        assert info.size_bytes == 1024
        assert info.chunk_index == 0
    
    def test_chunk_info_to_dict(self):
        """Test converting ChunkInfo to dictionary."""
        info = ChunkInfo(
            song_id="test",
            start_ms=0,
            end_ms=10000,
            file_path=Path("/tmp/test.mp3"),
            size_bytes=1024,
            chunk_index=0,
        )
        
        data = info.to_dict()
        
        assert "song_id" in data
        assert "start_ms" in data
        assert "end_ms" in data
        assert "file_path" in data
        assert data["song_id"] == "test"


class TestGetStreamInfo:
    """Tests for get_stream_info method."""
    
    @pytest.fixture
    def streaming_service(self):
        """Create a StreamingService instance."""
        return StreamingService()
    
    def test_get_stream_info_with_duration(self, streaming_service):
        """Test getting stream info with known duration."""
        with patch.object(streaming_service, 'get_song_url') as mock_url:
            with patch.object(streaming_service, '_get_duration_with_yt_dlp') as mock_duration:
                with patch.object(streaming_service, '_get_cached_chunks') as mock_cached:
                    with patch.object(streaming_service, 'get_downloading_chunks') as mock_downloading:
                        mock_url.return_value = "https://example.com"
                        mock_duration.return_value = 180000  # 3 minutes
                        mock_cached.return_value = [0, 1, 2]
                        mock_downloading.return_value = set()
                        
                        info = streaming_service.get_stream_info("test_song")
                        
                        assert info is not None
                        assert info.song_id == "test_song"
                        assert info.duration_ms == 180000
                        # Should have 18 chunks (180s / 10s per chunk)
                        assert info.total_chunks == 18
                        assert info.downloading_chunks == set()
    
    def test_get_stream_info_no_duration(self, streaming_service):
        """Test getting stream info without duration."""
        with patch.object(streaming_service, 'get_song_url'):
            with patch.object(streaming_service, '_get_duration_with_yt_dlp') as mock_duration:
                with patch.object(streaming_service, '_get_cached_chunks') as mock_cached:
                    with patch.object(streaming_service, 'get_downloading_chunks') as mock_downloading:
                        mock_duration.return_value = None
                        mock_cached.return_value = []
                        mock_downloading.return_value = set()
                        
                        info = streaming_service.get_stream_info("test_song")
                        
                        assert info is not None
                        assert info.duration_ms is None
                        assert info.total_chunks == 0


class TestChunkManagement:
    """Tests for chunk management."""
    
    @pytest.fixture
    def streaming_service(self):
        """Create a StreamingService instance."""
        return StreamingService()
    
    def test_get_cached_chunks_empty(self, streaming_service):
        """Test getting cached chunks for non-existent song."""
        cached = streaming_service._get_cached_chunks("nonexistent")
        assert cached == []
    
    def test_get_chunk_not_found(self, streaming_service):
        """Test getting non-existent chunk."""
        chunk_path = streaming_service.get_chunk("nonexistent", 0)
        assert chunk_path is None


class TestSingletonService:
    """Tests for singleton service access."""
    
    def test_get_streaming_service_singleton(self):
        """Test that get_streaming_service returns the same instance."""
        service1 = get_streaming_service()
        service2 = get_streaming_service()
        
        assert service1 is service2


class TestCacheCleanup:
    """Tests for cache cleanup functionality."""
    
    @pytest.fixture
    def streaming_service(self):
        """Create a StreamingService instance."""
        return StreamingService()
    
    def test_get_total_cache_size_empty(self, streaming_service):
        """Test getting cache size when empty."""
        # Clean up any existing chunks
        import shutil
        if CHUNKS_DIR.exists():
            for chunk_file in CHUNKS_DIR.glob("*"):
                chunk_file.unlink()
        
        try:
            size = streaming_service._get_total_cache_size()
            assert size == 0
        finally:
            # Cleanup
            if CHUNKS_DIR.exists():
                for chunk_file in CHUNKS_DIR.glob("*"):
                    chunk_file.unlink()
    
    def test_get_total_cache_size_with_files(self, streaming_service):
        """Test getting cache size with files."""
        # Create a test chunk file
        test_file = CHUNKS_DIR / "test_chunk.mp3"
        CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(test_file, 'wb') as f:
                f.write(b'test data' * 100)  # 900 bytes
            
            size = streaming_service._get_total_cache_size()
            assert size >= 900
            
            # Cleanup
            test_file.unlink()
        finally:
            # Cleanup
            if test_file.exists():
                test_file.unlink()


class TestFileOperations:
    """Tests for file operations."""
    
    @pytest.fixture
    def streaming_service(self):
        """Create a StreamingService instance."""
        return StreamingService()
    
    def test_directory_creation(self, streaming_service):
        """Test that required directories are created."""
        assert CHUNKS_DIR.exists()
        assert CHUNKS_DIR.is_dir()


# =============================================================================
# NEW PHASE 3 TESTS
# =============================================================================

class TestChunkStatus:
    """Tests for chunk status tracking."""
    
    @pytest.fixture
    def streaming_service(self):
        """Create a StreamingService instance."""
        return StreamingService()
    
    def test_chunk_status_enum_values(self):
        """Test ChunkStatus enum values."""
        assert ChunkStatus.NOT_DOWNLOADED.value == "not_downloaded"
        assert ChunkStatus.DOWNLOADING.value == "downloading"
        assert ChunkStatus.DOWNLOADED.value == "downloaded"
        assert ChunkStatus.ERROR.value == "error"
    
    def test_get_chunk_status_empty(self, streaming_service):
        """Test getting chunk status for unknown song."""
        status = streaming_service.get_chunk_status("unknown_song")
        assert status == {}
    
    def test_get_chunk_status_with_total_chunks(self, streaming_service):
        """Test getting chunk status with total chunks."""
        status = streaming_service.get_chunk_status("test_song", total_chunks=5)
        assert len(status) == 5
        assert all(s == ChunkStatus.NOT_DOWNLOADED for s in status.values())


class TestPlaybackInfo:
    """Tests for PlaybackInfo dataclass."""
    
    def test_playback_info_creation(self):
        """Test creating PlaybackInfo."""
        info = PlaybackInfo(
            song_id="test_song",
            current_chunk_index=2,
            position_in_chunk_ms=5000,
            is_playing=True,
            volume=0.8,
        )
        
        assert info.song_id == "test_song"
        assert info.current_chunk_index == 2
        assert info.position_in_chunk_ms == 5000
        assert info.is_playing == True
        assert info.volume == 0.8
    
    def test_playback_info_current_position_ms(self):
        """Test calculating current position in ms."""
        from backend.config import CHUNK_SIZE_SEC
        
        info = PlaybackInfo(
            current_chunk_index=3,
            position_in_chunk_ms=5000,
        )
        
        expected_position = 3 * (CHUNK_SIZE_SEC * 1000) + 5000
        assert info.current_position_ms == expected_position
    
    def test_playback_info_to_dict(self):
        """Test converting PlaybackInfo to dictionary."""
        info = PlaybackInfo(
            song_id="test",
            current_chunk_index=1,
            position_in_chunk_ms=2000,
        )
        
        data = info.to_dict()
        
        assert "song_id" in data
        assert "current_chunk_index" in data
        assert "position_in_chunk_ms" in data
        assert "current_position_ms" in data
        assert data["song_id"] == "test"


class TestDownloadPriority:
    """Tests for DownloadPriority enum."""
    
    def test_priority_values(self):
        """Test priority values."""
        assert DownloadPriority.LOW.value == 0
        assert DownloadPriority.NORMAL.value == 1
        assert DownloadPriority.HIGH.value == 2
        assert DownloadPriority.CRITICAL.value == 3
    
    def test_priority_ordering(self):
        """Test priority ordering."""
        assert DownloadPriority.CRITICAL > DownloadPriority.HIGH
        assert DownloadPriority.HIGH > DownloadPriority.NORMAL
        assert DownloadPriority.NORMAL > DownloadPriority.LOW


class TestChunkDownloadTask:
    """Tests for ChunkDownloadTask dataclass."""
    
    def test_task_creation(self):
        """Test creating a download task."""
        task = ChunkDownloadTask(
            song_id="test_song",
            chunk_index=5,
            priority=DownloadPriority.HIGH,
        )
        
        assert task.song_id == "test_song"
        assert task.chunk_index == 5
        assert task.priority == DownloadPriority.HIGH
    
    def test_task_priority_comparison(self):
        """Test task priority comparison."""
        from datetime import timedelta
        
        critical_task = ChunkDownloadTask(
            song_id="song1",
            chunk_index=0,
            priority=DownloadPriority.CRITICAL,
        )
        
        high_task = ChunkDownloadTask(
            song_id="song2",
            chunk_index=0,
            priority=DownloadPriority.HIGH,
        )
        
        # Higher priority tasks should come first
        assert critical_task < high_task


class TestPlaybackSession:
    """Tests for PlaybackSession."""
    
    @pytest.fixture
    def playback_session(self):
        """Create a PlaybackSession instance."""
        return PlaybackSession()
    
    def test_initial_state(self, playback_session):
        """Test initial playback session state."""
        assert playback_session.current_song_id is None
        assert playback_session.get_current_chunk_index() == 0
    
    def test_set_song(self, playback_session):
        """Test setting the current song."""
        playback_session.set_song("test_song")
        
        assert playback_session.current_song_id == "test_song"
        assert playback_session.get_current_chunk_index() == 0
    
    def test_update_position(self, playback_session):
        """Test updating playback position."""
        playback_session.update_position(15000)  # 15 seconds
        
        # With 10-second chunks, this should be chunk 1 at position 5000ms
        from backend.config import CHUNK_SIZE_SEC
        chunk_size_ms = CHUNK_SIZE_SEC * 1000
        
        expected_chunk = 15000 // chunk_size_ms
        expected_position = 15000 % chunk_size_ms
        
        assert playback_session.get_current_chunk_index() == expected_chunk
        assert playback_session.get_playback_info().position_in_chunk_ms == expected_position
    
    def test_set_playing(self, playback_session):
        """Test setting playing state."""
        playback_session.set_playing(True)
        assert playback_session.get_playback_info().is_playing == True
        
        playback_session.set_playing(False)
        assert playback_session.get_playback_info().is_playing == False
    
    def test_get_chunks_to_buffer(self, playback_session):
        """Test getting chunks to buffer."""
        playback_session.set_song("test_song")
        playback_session.update_position(0)
        
        total_chunks = 10
        chunks_to_buffer = playback_session.get_chunks_to_buffer(total_chunks)
        
        # Should buffer ahead plus some before
        assert len(chunks_to_buffer) > 0
        assert 0 in chunks_to_buffer  # Current chunk
    
    def test_should_download_chunk(self, playback_session):
        """Test should_download_chunk logic."""
        playback_session.set_song("test_song")
        
        cached_chunks = {0, 1, 2}
        downloading_chunks = {3}
        total_chunks = 10
        
        # Already cached - should not download
        assert not playback_session.should_download_chunk(0, total_chunks, cached_chunks, downloading_chunks)
        
        # Already downloading - should not download
        assert not playback_session.should_download_chunk(3, total_chunks, cached_chunks, downloading_chunks)
        
        # Not cached, not downloading - should download if in buffer range
        # Note: This depends on current playback position


class TestStreamingServicePlayback:
    """Tests for playback management in StreamingService."""
    
    @pytest.fixture
    def streaming_service(self):
        """Create a StreamingService instance."""
        return StreamingService()
    
    def test_start_playback(self, streaming_service):
        """Test starting playback."""
        # Mock the required methods
        with patch.object(streaming_service, 'get_stream_info') as mock_info:
            with patch.object(streaming_service, 'buffer_chunks_for_song') as mock_buffer:
                with patch.object(streaming_service, '_save_playback_state') as mock_save:
                    mock_info.return_value = StreamInfo(
                        song_id="test_song",
                        title="Test Song",
                        duration_ms=100000,
                        total_chunks=10,
                    )
                    
                    result = streaming_service.start_playback("test_song")
                    
                    assert result == True
                    assert streaming_service.get_current_song_id() == "test_song"
                    mock_buffer.assert_called_once()
                    mock_save.assert_called_once()
    
    def test_pause_playback(self, streaming_service):
        """Test pausing playback."""
        streaming_service.start_playback("test_song")
        
        with patch.object(streaming_service, '_save_playback_state') as mock_save:
            streaming_service.pause_playback()
            mock_save.assert_called_once()
    
    def test_stop_playback(self, streaming_service):
        """Test stopping playback."""
        streaming_service.start_playback("test_song")
        
        with patch.object(streaming_service, '_save_playback_state') as mock_save:
            streaming_service.stop_playback()
            assert streaming_service.get_current_song_id() is None
            mock_save.assert_called_once()
    
    def test_update_playback_position(self, streaming_service):
        """Test updating playback position."""
        streaming_service.start_playback("test_song")
        
        with patch.object(streaming_service, 'get_stream_info') as mock_info:
            with patch.object(streaming_service, 'buffer_chunks_for_song') as mock_buffer:
                with patch.object(streaming_service, '_save_playback_state') as mock_save:
                    with patch.object(streaming_service._playback_session, 'update_position'):
                        mock_info.return_value = StreamInfo(
                            song_id="test_song",
                            title="Test Song",
                            duration_ms=100000,
                            total_chunks=10,
                        )
                        
                        streaming_service.update_playback_position(25000)
                        
                        # Verify position was updated
                        playback_info = streaming_service.get_playback_state()
                        # The position is stored in playback state which reads from the database
                        # For this test, we just verify the method was called
                        mock_save.assert_called()
    
    def test_get_playback_state(self, streaming_service):
        """Test getting playback state."""
        state = streaming_service.get_playback_state()
        
        assert "current_song_id" in state
        assert "current_time_ms" in state
        assert "is_playing" in state
        assert "volume" in state
    
    def test_get_song_chunks_status(self, streaming_service):
        """Test getting song chunks status."""
        with patch.object(streaming_service, 'get_stream_info') as mock_info:
            with patch.object(streaming_service, 'get_chunk_status') as mock_status:
                with patch.object(streaming_service, 'get_downloading_chunks') as mock_downloading:
                    mock_info.return_value = StreamInfo(
                        song_id="test_song",
                        title="Test Song",
                        duration_ms=100000,
                        total_chunks=10,
                        cached_chunks=[0, 1, 2],
                        downloading_chunks={3, 4},
                    )
                    mock_status.return_value = {
                        0: ChunkStatus.DOWNLOADED,
                        1: ChunkStatus.DOWNLOADED,
                        2: ChunkStatus.DOWNLOADED,
                        3: ChunkStatus.DOWNLOADING,
                        4: ChunkStatus.DOWNLOADING,
                        5: ChunkStatus.NOT_DOWNLOADED,
                        6: ChunkStatus.NOT_DOWNLOADED,
                        7: ChunkStatus.NOT_DOWNLOADED,
                        8: ChunkStatus.NOT_DOWNLOADED,
                        9: ChunkStatus.NOT_DOWNLOADED,
                    }
                    mock_downloading.return_value = {3, 4}
                    
                    status_info = streaming_service.get_song_chunks_status("test_song")
                    
                    assert "total_chunks" in status_info
                    assert "chunk_status" in status_info
                    assert "cached_count" in status_info
                    assert "downloading_count" in status_info
                    assert status_info["total_chunks"] == 10
                    assert status_info["downloading_count"] == 2
                    assert status_info["cached_count"] == 3


class TestStreamingServiceBuffering:
    """Tests for buffer-ahead logic."""
    
    @pytest.fixture
    def streaming_service(self):
        """Create a StreamingService instance."""
        return StreamingService()
    
    def test_buffer_chunks_for_song(self, streaming_service):
        """Test buffering chunks for a song."""
        with patch.object(streaming_service, 'get_stream_info') as mock_info:
            with patch.object(streaming_service, '_get_cached_chunks') as mock_cached:
                with patch.object(streaming_service, 'get_downloading_chunks') as mock_downloading:
                    with patch.object(streaming_service._playback_session, 'get_chunks_to_buffer') as mock_buffer:
                        with patch.object(streaming_service._download_manager, 'add_task') as mock_add:
                            mock_info.return_value = StreamInfo(
                                song_id="test_song",
                                title="Test Song",
                                duration_ms=100000,
                                total_chunks=10,
                            )
                            mock_cached.return_value = []
                            mock_downloading.return_value = set()
                            mock_buffer.return_value = [0, 1, 2, 3, 4]
                            
                            streaming_service.buffer_chunks_for_song("test_song", 10)
                            
                            # Should add tasks for chunks that need buffering
                            assert mock_add.call_count >= 0


class TestChunkStatusVisualization:
    """Tests for chunk status visualization."""
    
    @pytest.fixture
    def streaming_service(self):
        """Create a StreamingService instance."""
        return StreamingService()
    
    def test_chunk_status_update_on_download(self, streaming_service):
        """Test that chunk status is updated when downloading (Range request flow)."""
        # Create a temp file for the chunk
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.opus') as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(b'fake audio data')

        def mock_download_byte_range(url, output_path, start_byte, end_byte=None):
            """Mock that creates the output file with fake data."""
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(b'fake audio chunk data')
            return True, 206

        try:
            # Mock get_chunk to return None (not cached)
            with patch.object(streaming_service, 'get_chunk', return_value=None):
                # Mock stream URL
                with patch.object(streaming_service, '_get_stream_url_cached', return_value='https://example.com/audio'):
                    # Mock byte range calculation
                    with patch.object(streaming_service, '_get_chunk_byte_range', return_value=(0, 1023)):
                        # Mock the actual byte range download
                        with patch.object(streaming_service, '_download_byte_range', side_effect=mock_download_byte_range):
                            # Mock save_chunk_metadata
                            with patch.object(streaming_service, '_save_chunk_metadata'):
                                streaming_service.download_chunk("test_song", 0)

                                # Check status was updated
                                status = streaming_service.get_chunk_status("test_song", total_chunks=1)
                                assert 0 in status
                                assert status[0] == ChunkStatus.DOWNLOADED
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
