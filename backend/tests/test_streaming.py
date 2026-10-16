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
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.streaming import (
    StreamingService,
    ChunkInfo,
    StreamInfo,
    get_streaming_service,
    QUALITY_PRESETS,
)
from backend.config import CHUNKS_DIR, CACHE_DIR, CHUNK_SIZE_SEC


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
                mock_url.return_value = "https://example.com"
                mock_duration.return_value = 180000  # 3 minutes
                
                info = streaming_service.get_stream_info("test_song")
                
                assert info is not None
                assert info.song_id == "test_song"
                assert info.duration_ms == 180000
                # Should have 18 chunks (180s / 10s per chunk)
                assert info.total_chunks == 18
    
    def test_get_stream_info_no_duration(self, streaming_service):
        """Test getting stream info without duration."""
        with patch.object(streaming_service, 'get_song_url'):
            with patch.object(streaming_service, '_get_duration_with_yt_dlp') as mock_duration:
                mock_duration.return_value = None
                
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
