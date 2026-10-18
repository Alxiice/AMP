"""
Streaming Service
================
Service layer for audio streaming from YouTube using yt-dlp.

This service provides:
- Chunk downloading from YouTube
- Format and quality selection
- Chunk caching and management
- Streaming endpoint support
- Playback state management
- Buffer-ahead logic
- LRU cache eviction
- Parallel downloads
"""

import os
import re
import subprocess
import tempfile
import threading
import queue
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, BinaryIO, Set, Callable
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
import hashlib
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio

from backend.config import (
    BASE_DIR,
    CACHE_DIR,
    CHUNKS_DIR,
    CHUNK_SIZE_SEC,
    AUDIO_FORMAT,
    AUDIO_BITRATE,
    AUDIO_QUALITY,
    CACHE_MAX_SIZE_MB,
    DEBUG,
    BUFFER_AHEAD_SEC,
)

from backend.database.session import get_userdb_session, get_playdb_session
from backend.database.models import Song, CachedChunk, PlaybackState, RepeatMode
from backend.utils.logger import get_logger

logger = get_logger(__name__)


# Singleton instance
_streaming_service_instance = None
_download_executor = None
_download_lock = threading.Lock()


def get_streaming_service() -> "StreamingService":
    """Get the singleton StreamingService instance."""
    global _streaming_service_instance
    if _streaming_service_instance is None:
        _streaming_service_instance = StreamingService()
    return _streaming_service_instance


# Quality presets for yt-dlp
QUALITY_PRESETS = {
    "low": {
        "format": "bestaudio[abr<=96]/best",
        "bitrate": 96,
        "file_ext": "opus",
    },
    "medium": {
        "format": "bestaudio[abr<=128]/best",
        "bitrate": 128,
        "file_ext": "opus",
    },
    "high": {
        "format": "bestaudio[abr<=192]/best",
        "bitrate": 192,
        "file_ext": "mp3",
    },
    "best": {
        "format": "bestaudio/best",
        "bitrate": 320,
        "file_ext": "mp3",
    },
}


class ChunkStatus(str, Enum):
    """Status of a chunk."""
    NOT_DOWNLOADED = "not_downloaded"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    ERROR = "error"


class DownloadPriority(int, Enum):
    """Priority levels for chunk downloads."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class ChunkInfo:
    """Information about a cached audio chunk."""
    song_id: str
    start_ms: int
    end_ms: int
    file_path: Path
    size_bytes: int
    chunk_index: int
    status: ChunkStatus = ChunkStatus.NOT_DOWNLOADED
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class StreamInfo:
    """Information about a stream."""
    song_id: str
    title: str
    duration_ms: Optional[int] = None
    mime_type: str = "audio/mpeg"
    chunk_size_ms: int = CHUNK_SIZE_SEC * 1000
    total_chunks: int = 0
    cached_chunks: List[int] = None
    downloading_chunks: Set[int] = field(default_factory=set)
    
    def __post_init__(self):
        if self.cached_chunks is None:
            self.cached_chunks = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class PlaybackInfo:
    """Information about current playback."""
    song_id: Optional[str] = None
    current_chunk_index: int = 0
    position_in_chunk_ms: int = 0
    is_playing: bool = False
    volume: float = 1.0
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def current_position_ms(self) -> int:
        """Get the current position in milliseconds."""
        return self.current_chunk_index * (CHUNK_SIZE_SEC * 1000) + self.position_in_chunk_ms
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "song_id": self.song_id,
            "current_chunk_index": self.current_chunk_index,
            "position_in_chunk_ms": self.position_in_chunk_ms,
            "current_position_ms": self.current_position_ms,
            "is_playing": self.is_playing,
            "volume": self.volume,
            "last_updated": self.last_updated.isoformat(),
        }


@dataclass
class ChunkDownloadTask:
    """A task for downloading a chunk."""
    song_id: str
    chunk_index: int
    priority: DownloadPriority = DownloadPriority.NORMAL
    callback: Optional[Callable[[bool, Path, int], None]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def __lt__(self, other: "ChunkDownloadTask") -> bool:
        """Compare tasks by priority (higher priority first)."""
        # Higher priority comes first, then by creation time
        if self.priority != other.priority:
            return self.priority.value > other.priority.value
        return self.created_at < other.created_at


class PlaybackSession:
    """Manages playback state for a session."""
    
    def __init__(self):
        self.current_song_id: Optional[str] = None
        self.playback_info = PlaybackInfo()
        self.buffer_ahead_chunks: int = BUFFER_AHEAD_SEC // CHUNK_SIZE_SEC
        self.min_buffer_chunks: int = max(2, self.buffer_ahead_chunks - 1)
        self._lock = threading.Lock()
    
    def update_position(self, position_ms: int) -> None:
        """Update the current playback position."""
        chunk_size_ms = CHUNK_SIZE_SEC * 1000
        chunk_index = position_ms // chunk_size_ms
        position_in_chunk = position_ms % chunk_size_ms
        
        with self._lock:
            self.playback_info.current_chunk_index = chunk_index
            self.playback_info.position_in_chunk_ms = position_in_chunk
            self.playback_info.last_updated = datetime.utcnow()
    
    def set_song(self, song_id: str) -> None:
        """Set the current song."""
        with self._lock:
            self.current_song_id = song_id
            self.playback_info.song_id = song_id
            self.playback_info.current_chunk_index = 0
            self.playback_info.position_in_chunk_ms = 0
    
    def set_playing(self, is_playing: bool) -> None:
        """Set playback state."""
        with self._lock:
            self.playback_info.is_playing = is_playing
            self.playback_info.last_updated = datetime.utcnow()
    
    def get_current_chunk_index(self) -> int:
        """Get the current chunk index."""
        with self._lock:
            return self.playback_info.current_chunk_index
    
    def get_playback_info(self) -> PlaybackInfo:
        """Get current playback info."""
        with self._lock:
            return self.playback_info
    
    def get_chunks_to_buffer(self, total_chunks: int) -> List[int]:
        """Get the list of chunks that should be buffered."""
        current_chunk = self.get_current_chunk_index()
        chunks_to_buffer = []
        
        # Buffer ahead from current position
        for offset in range(self.buffer_ahead_chunks + 1):
            chunk_idx = current_chunk + offset
            if chunk_idx < total_chunks:
                chunks_to_buffer.append(chunk_idx)
        
        # Also buffer a few before current position for seeking
        for offset in range(1, 3):
            chunk_idx = current_chunk - offset
            if chunk_idx >= 0:
                chunks_to_buffer.insert(0, chunk_idx)
        
        return chunks_to_buffer
    
    def should_download_chunk(self, chunk_index: int, total_chunks: int, cached_chunks: Set[int], downloading_chunks: Set[int]) -> bool:
        """Determine if a chunk should be downloaded."""
        if chunk_index >= total_chunks:
            return False
        if chunk_index in cached_chunks:
            return False
        if chunk_index in downloading_chunks:
            return False
        
        # Check if it's in our buffer range
        chunks_to_buffer = self.get_chunks_to_buffer(total_chunks)
        return chunk_index in chunks_to_buffer


class DownloadManager:
    """Manages parallel chunk downloads with priority queue."""
    
    def __init__(self, max_workers: int = 3):
        self.max_workers = max_workers
        self.task_queue: queue.PriorityQueue = queue.PriorityQueue()
        self.active_downloads: Dict[Tuple[str, int], bool] = {}
        self._lock = threading.Lock()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._shutdown = False
    
    def start(self) -> None:
        """Start the download manager."""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
            self._shutdown = False
            # Start worker threads
            for _ in range(self.max_workers):
                threading.Thread(target=self._worker, daemon=True).start()
    
    def stop(self) -> None:
        """Stop the download manager."""
        self._shutdown = True
        if self._executor:
            self._executor.shutdown(wait=False)
            self._executor = None
    
    def _worker(self) -> None:
        """Worker thread that processes download tasks."""
        while not self._shutdown:
            try:
                # Get next task with timeout to allow shutdown check
                task = self.task_queue.get(timeout=1)
                self._process_task(task)
                self.task_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in download worker: {e}")
    
    def _process_task(self, task: ChunkDownloadTask) -> None:
        """Process a download task."""
        key = (task.song_id, task.chunk_index)
        
        with self._lock:
            if key in self.active_downloads:
                # Already being downloaded
                return
            self.active_downloads[key] = True
        
        try:
            logger.debug(f"Processing download task: {task.song_id} [{task.chunk_index}]")
            
            # Get the streaming service
            service = get_streaming_service()
            
            # Download the chunk
            chunk_path = service.download_chunk(task.song_id, task.chunk_index)
            
            # Call callback if provided
            if task.callback:
                task.callback(chunk_path is not None, chunk_path or Path(""), task.chunk_index)
                
        except Exception as e:
            logger.error(f"Failed to process download task: {e}")
            if task.callback:
                task.callback(False, Path(""), task.chunk_index)
        finally:
            with self._lock:
                if key in self.active_downloads:
                    del self.active_downloads[key]
    
    def add_task(self, task: ChunkDownloadTask) -> None:
        """Add a download task to the queue."""
        self.task_queue.put(task)
    
    def is_downloading(self, song_id: str, chunk_index: int) -> bool:
        """Check if a chunk is currently being downloaded."""
        with self._lock:
            return (song_id, chunk_index) in self.active_downloads
    
    def get_downloading_chunks(self, song_id: str) -> Set[int]:
        """Get set of chunks currently being downloaded for a song."""
        with self._lock:
            return {idx for (sid, idx) in self.active_downloads.keys() if sid == song_id}


class StreamingService:
    """
    Service class for audio streaming from YouTube.
    
    Uses yt-dlp to download and cache audio chunks.
    """
    
    def __init__(self):
        """Initialize the StreamingService."""
        self._quality_preset = QUALITY_PRESETS.get(AUDIO_QUALITY.lower(), QUALITY_PRESETS["high"])
        self._chunk_size_ms = CHUNK_SIZE_SEC * 1000
        self._cache_max_size_bytes = CACHE_MAX_SIZE_MB * 1024 * 1024
        
        # Ensure directories exist
        os.makedirs(CHUNKS_DIR, exist_ok=True)
        
        # Initialize download manager
        self._download_manager = DownloadManager(max_workers=4)
        self._download_manager.start()
        
        # Initialize playback session
        self._playback_session = PlaybackSession()
        
        # Track currently downloading chunks per song
        self._downloading_chunks: Dict[str, Set[int]] = {}
        self._downloading_lock = threading.Lock()
        
        # Track chunk status for visualization
        self._chunk_status: Dict[str, Dict[int, ChunkStatus]] = {}
        self._status_lock = threading.Lock()
        
        # Initialize chunk cache tracking
        self._initialize_chunk_cache()
        
        logger.info(f"StreamingService initialized: quality={AUDIO_QUALITY}, chunk_size={CHUNK_SIZE_SEC}s")
    
    def _initialize_chunk_cache(self) -> None:
        """Initialize chunk cache from database."""
        try:
            db = next(get_userdb_session())
            chunks = db.query(CachedChunk).all()
            
            for chunk in chunks:
                song_id = chunk.song_id
                chunk_index = self._get_chunk_index(chunk.start_ms)
                
                with self._status_lock:
                    if song_id not in self._chunk_status:
                        self._chunk_status[song_id] = {}
                    self._chunk_status[song_id][chunk_index] = ChunkStatus.DOWNLOADED
            
            logger.info(f"Initialized chunk cache: {len(chunks)} chunks")
            
        except Exception as e:
            logger.error(f"Failed to initialize chunk cache: {e}")
    
    def _get_yt_dlp_path(self) -> str:
        """Get the path to yt-dlp executable."""
        # Check if yt-dlp is in PATH
        import shutil
        yt_dlp = shutil.which("yt-dlp")
        if yt_dlp:
            return yt_dlp
        
        # Check common locations
        common_paths = [
            "yt-dlp",
            "yt-dlp.exe",
            str(BASE_DIR / "venv" / "Scripts" / "yt-dlp.exe"),
            str(BASE_DIR / "venv" / "bin" / "yt-dlp"),
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                return path
        
        # Fallback to direct execution
        return "yt-dlp"
    
    def _generate_chunk_filename(self, song_id: str, chunk_index: int) -> Path:
        """Generate a unique filename for a chunk."""
        # Sanitize song_id
        safe_song_id = re.sub(r"[^\w\-\.]", "_", song_id)
        
        # Use the file extension from the quality preset
        file_ext = self._quality_preset.get("file_ext", "mp3")
        
        filename = f"{safe_song_id}_{chunk_index:04d}.{file_ext}"
        
        return CHUNKS_DIR / filename
    
    def _get_chunk_index(self, start_ms: int) -> int:
        """Get the chunk index for a given start position in milliseconds."""
        return start_ms // self._chunk_size_ms
    
    def _get_chunk_range(self, start_ms: int) -> Tuple[int, int]:
        """Get the start and end milliseconds for a chunk."""
        chunk_index = self._get_chunk_index(start_ms)
        chunk_start_ms = chunk_index * self._chunk_size_ms
        chunk_end_ms = chunk_start_ms + self._chunk_size_ms
        return chunk_start_ms, chunk_end_ms
    
    def _download_audio(
        self,
        url: str,
        output_path: Path,
        format_str: str = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> bool:
        """
        Download audio from a URL using yt-dlp.
        
        Args:
            url: YouTube URL or video ID
            output_path: Path to save the downloaded file
            format_str: Format string for yt-dlp
            start_time: Start time for partial download (HH:MM:SS or seconds)
            end_time: End time for partial download (HH:MM:SS or seconds)
            
        Returns:
            True if download succeeded, False otherwise
        """
        try:
            yt_dlp = self._get_yt_dlp_path()
            
            # Ensure output directory exists
            os.makedirs(output_path.parent, exist_ok=True)
            
            # Build command
            cmd = [
                yt_dlp,
                "--quiet",
                "--no-warnings",
                "--no-progress",
                "--output", str(output_path),
            ]
            
            # Add format
            if format_str:
                cmd.extend(["--format", format_str])
            else:
                cmd.extend(["--format", self._quality_preset["format"]])
            
            # Add audio format
            cmd.extend([
                "--extract-audio",
                "--audio-format", AUDIO_FORMAT,
                "--audio-quality", str(AUDIO_BITRATE),
            ])
            
            # Add start and end time if specified
            if start_time:
                cmd.extend(["--download-sections", f"*{start_time}-{end_time}" if end_time else f"*{start_time}"])
            
            # Add URL
            cmd.append(url)
            
            logger.debug(f"Running yt-dlp command: {' '.join(cmd)}")
            
            # Run command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,  # 2 minute timeout
            )
            
            if result.returncode != 0:
                logger.error(f"yt-dlp failed: {result.stderr}")
                return False
            
            # Check if file was created
            if not output_path.exists():
                logger.error(f"Output file not created: {output_path}")
                return False
            
            logger.info(f"Downloaded audio to: {output_path}")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("yt-dlp download timed out")
            return False
        except Exception as e:
            logger.error(f"Failed to download audio: {e}")
            return False
    
    def _ms_to_time_str(self, ms: int) -> str:
        """Convert milliseconds to HH:MM:SS format for yt-dlp."""
        seconds = ms // 1000
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    
    def get_song_url(self, song_id: str) -> str:
        """Generate a YouTube URL from a song ID."""
        if "youtube.com" in song_id or "youtu.be" in song_id:
            return song_id
        return f"https://www.youtube.com/watch?v={song_id}"
    
    def get_stream_info(self, song_id: str) -> Optional[StreamInfo]:
        """
        Get information about a stream.
        
        Args:
            song_id: YouTube video ID
            
        Returns:
            StreamInfo object or None if failed
        """
        try:
            # First, get song metadata to get duration
            from backend.services.youtube import YouTubeService, get_youtube_service
            youtube = get_youtube_service()
            song_metadata = youtube.get_song_metadata(song_id)
            
            if not song_metadata:
                # Try to get duration from yt-dlp
                duration_ms = self._get_duration_with_yt_dlp(song_id)
            else:
                duration_ms = song_metadata.duration_ms
            
            # Calculate total chunks
            if duration_ms:
                total_chunks = (duration_ms + self._chunk_size_ms - 1) // self._chunk_size_ms
            else:
                total_chunks = 0
            
            # Get cached chunks
            cached_chunks = self._get_cached_chunks(song_id)
            
            # Get downloading chunks
            downloading_chunks = self.get_downloading_chunks(song_id)
            
            # Get chunk status for this song
            chunk_status = self.get_chunk_status(song_id, total_chunks)
            
            return StreamInfo(
                song_id=song_id,
                title=song_metadata.title if song_metadata else song_id,
                duration_ms=duration_ms,
                total_chunks=total_chunks,
                cached_chunks=cached_chunks,
                downloading_chunks=downloading_chunks,
            )
            
        except Exception as e:
            logger.error(f"Failed to get stream info: {e}")
            return None
    
    def get_chunk_status(self, song_id: str, total_chunks: Optional[int] = None) -> Dict[int, ChunkStatus]:
        """
        Get the status of all chunks for a song.
        
        Args:
            song_id: YouTube video ID
            total_chunks: Optional total number of chunks
            
        Returns:
            Dictionary mapping chunk index to ChunkStatus
        """
        with self._status_lock:
            if song_id in self._chunk_status:
                if total_chunks is not None:
                    # Ensure all chunks up to total_chunks are represented
                    for i in range(total_chunks):
                        if i not in self._chunk_status[song_id]:
                            self._chunk_status[song_id][i] = ChunkStatus.NOT_DOWNLOADED
                    # Remove extra chunks beyond total
                    self._chunk_status[song_id] = {
                        k: v for k, v in self._chunk_status[song_id].items() if k < total_chunks
                    }
                return self._chunk_status.get(song_id, {}).copy()
            else:
                # Initialize if not exists
                status = {}
                if total_chunks is not None:
                    for i in range(total_chunks):
                        status[i] = ChunkStatus.NOT_DOWNLOADED
                self._chunk_status[song_id] = status
                return status.copy()
    
    def get_downloading_chunks(self, song_id: str) -> Set[int]:
        """Get the set of chunk indices currently being downloaded for a song."""
        with self._downloading_lock:
            return self._downloading_chunks.get(song_id, set()).copy()
    
    def _get_duration_with_yt_dlp(self, song_id: str) -> Optional[int]:
        """Get the duration of a video using yt-dlp."""
        try:
            yt_dlp = self._get_yt_dlp_path()
            url = self.get_song_url(song_id)
            
            cmd = [
                yt_dlp,
                "--quiet",
                "--no-warnings",
                "--no-progress",
                "--get-duration",
                url,
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode == 0 and result.stdout:
                # Duration is in seconds
                duration_sec = float(result.stdout.strip())
                return int(duration_sec * 1000)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get duration with yt-dlp: {e}")
            return None
    
    def _get_cached_chunks(self, song_id: str) -> List[int]:
        """Get list of cached chunk indices for a song."""
        try:
            db = next(get_userdb_session())
            chunks = db.query(CachedChunk).filter(CachedChunk.song_id == song_id).all()
            
            # Extract chunk indices from start_ms
            cached_indices = []
            for chunk in chunks:
                chunk_index = self._get_chunk_index(chunk.start_ms)
                cached_indices.append(chunk_index)
            
            return cached_indices
            
        except Exception as e:
            logger.error(f"Failed to get cached chunks: {e}")
            return []
    
    def get_chunk(self, song_id: str, chunk_index: int) -> Optional[Path]:
        """
        Get a chunk file for a song.
        
        Args:
            song_id: YouTube video ID
            chunk_index: Chunk index (0-based)
            
        Returns:
            Path to the chunk file or None if not found
        """
        try:
            db = next(get_userdb_session())
            
            # Calculate start and end ms
            start_ms = chunk_index * self._chunk_size_ms
            end_ms = start_ms + self._chunk_size_ms
            
            # Find chunk in database
            chunk = db.query(CachedChunk).filter(
                CachedChunk.song_id == song_id,
                CachedChunk.start_ms == start_ms,
            ).first()
            
            if chunk and os.path.exists(chunk.file_path):
                return Path(chunk.file_path)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get chunk: {e}")
            return None
    
    def download_chunk(self, song_id: str, chunk_index: int, force: bool = False, mark_downloading: bool = True) -> Optional[Path]:
        """
        Download a specific chunk of a song.
        
        Args:
            song_id: YouTube video ID
            chunk_index: Chunk index (0-based)
            force: Force re-download even if cached
            mark_downloading: Whether to mark chunk as downloading in status
            
        Returns:
            Path to the downloaded chunk or None if failed
        """
        try:
            url = self.get_song_url(song_id)
            
            # Calculate start and end ms
            start_ms = chunk_index * self._chunk_size_ms
            end_ms = start_ms + self._chunk_size_ms
            
            # Check if chunk already exists and is not forced
            existing_chunk = self.get_chunk(song_id, chunk_index)
            if existing_chunk and not force:
                logger.debug(f"Chunk already cached: {song_id} [{chunk_index}]")
                with self._status_lock:
                    if song_id not in self._chunk_status:
                        self._chunk_status[song_id] = {}
                    self._chunk_status[song_id][chunk_index] = ChunkStatus.DOWNLOADED
                return existing_chunk
            
            # Mark as downloading
            if mark_downloading:
                with self._downloading_lock:
                    if song_id not in self._downloading_chunks:
                        self._downloading_chunks[song_id] = set()
                    self._downloading_chunks[song_id].add(chunk_index)
                
                with self._status_lock:
                    if song_id not in self._chunk_status:
                        self._chunk_status[song_id] = {}
                    self._chunk_status[song_id][chunk_index] = ChunkStatus.DOWNLOADING
            
            # Generate output path
            output_path = self._generate_chunk_filename(song_id, chunk_index)
            
            # Convert ms to time string
            start_time_str = self._ms_to_time_str(start_ms)
            end_time_str = self._ms_to_time_str(end_ms)
            
            logger.info(f"Downloading chunk: {song_id} [{chunk_index}] ({start_time_str}-{end_time_str})")
            
            # Download the chunk
            success = self._download_audio(
                url=url,
                output_path=output_path,
                start_time=start_time_str,
                end_time=end_time_str,
            )
            
            # Clean up downloading state
            if mark_downloading:
                with self._downloading_lock:
                    if song_id in self._downloading_chunks:
                        self._downloading_chunks[song_id].discard(chunk_index)
            
            if not success:
                with self._status_lock:
                    if song_id in self._chunk_status:
                        self._chunk_status[song_id][chunk_index] = ChunkStatus.ERROR
                logger.error(f"Failed to download chunk: {song_id} [{chunk_index}]")
                return None
            
            # Save chunk metadata to database
            self._save_chunk_metadata(song_id, start_ms, end_ms, output_path)
            
            # Update status
            with self._status_lock:
                if song_id in self._chunk_status:
                    self._chunk_status[song_id][chunk_index] = ChunkStatus.DOWNLOADED
            
            logger.info(f"Chunk downloaded: {song_id} [{chunk_index}] -> {output_path}")
            return output_path
            
        except Exception as e:
            if mark_downloading:
                with self._downloading_lock:
                    if song_id in self._downloading_chunks:
                        self._downloading_chunks[song_id].discard(chunk_index)
                
                with self._status_lock:
                    if song_id in self._chunk_status:
                        self._chunk_status[song_id][chunk_index] = ChunkStatus.ERROR
            
            logger.error(f"Failed to download chunk: {e}")
            return None
    
    def _save_chunk_metadata(
        self,
        song_id: str,
        start_ms: int,
        end_ms: int,
        file_path: Path,
    ) -> None:
        """Save chunk metadata to database."""
        try:
            db = next(get_userdb_session())
            
            # Get file size
            if os.path.exists(file_path):
                size_bytes = os.path.getsize(file_path)
            else:
                size_bytes = 0
            
            # Create or update chunk record
            chunk = db.query(CachedChunk).filter(
                CachedChunk.song_id == song_id,
                CachedChunk.start_ms == start_ms,
            ).first()
            
            if chunk:
                chunk.file_path = str(file_path)
                chunk.size_bytes = size_bytes
                chunk.end_ms = end_ms
                chunk.last_accessed = datetime.utcnow()
            else:
                chunk = CachedChunk(
                    song_id=song_id,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    file_path=str(file_path),
                    size_bytes=size_bytes,
                )
                db.add(chunk)
            
            db.commit()
            db.refresh(chunk)
            
            logger.debug(f"Saved chunk metadata: {song_id} [{start_ms}-{end_ms}]")
            
        except Exception as e:
            logger.error(f"Failed to save chunk metadata: {e}")
    
    def get_chunk_data(self, song_id: str, chunk_index: int) -> Optional[bytes]:
        """
        Get the raw data for a chunk.
        
        Args:
            song_id: YouTube video ID
            chunk_index: Chunk index (0-based)
            
        Returns:
            Chunk data as bytes or None if not found
        """
        try:
            chunk_path = self.get_chunk(song_id, chunk_index)
            
            if chunk_path and os.path.exists(chunk_path):
                with open(chunk_path, "rb") as f:
                    return f.read()
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get chunk data: {e}")
            return None
    
    def get_chunk_bytes_range(self, song_id: str, chunk_index: int, start_byte: int = None, end_byte: int = None) -> Optional[bytes]:
        """
        Get a range of bytes from a chunk file.
        
        Args:
            song_id: YouTube video ID
            chunk_index: Chunk index (0-based)
            start_byte: Start byte (inclusive, default 0)
            end_byte: End byte (exclusive, default end of file)
            
        Returns:
            Chunk data as bytes or None if not found
        """
        try:
            chunk_path = self.get_chunk(song_id, chunk_index)
            
            if chunk_path and os.path.exists(chunk_path):
                file_size = os.path.getsize(chunk_path)
                
                if start_byte is None:
                    start_byte = 0
                if end_byte is None:
                    end_byte = file_size
                
                # Clamp to valid range
                start_byte = max(0, min(start_byte, file_size - 1))
                end_byte = max(start_byte, min(end_byte, file_size))
                
                with open(chunk_path, "rb") as f:
                    f.seek(start_byte)
                    return f.read(end_byte - start_byte)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get chunk bytes range: {e}")
            return None
    
    def buffer_chunks_for_song(self, song_id: str, total_chunks: Optional[int] = None) -> None:
        """
        Start buffering chunks for a song based on current playback position.
        
        This will download chunks in parallel based on buffer-ahead settings.
        
        Args:
            song_id: YouTube video ID
            total_chunks: Optional total number of chunks (if not provided, will be calculated)
        """
        try:
            if total_chunks is None:
                stream_info = self.get_stream_info(song_id)
                if stream_info:
                    total_chunks = stream_info.total_chunks
                else:
                    logger.error(f"Could not get stream info for: {song_id}")
                    return
            
            if total_chunks == 0:
                logger.warning(f"No chunks to buffer for song: {song_id}")
                return
            
            # Get current playback position
            current_chunk = self._playback_session.get_current_chunk_index()
            
            # Determine which chunks to buffer
            chunks_to_buffer = self._playback_session.get_chunks_to_buffer(total_chunks)
            
            # Get already cached chunks
            cached_chunks = set(self._get_cached_chunks(song_id))
            
            # Get currently downloading chunks
            downloading_chunks = self.get_downloading_chunks(song_id)
            
            # Queue downloads for chunks that need buffering
            for chunk_index in chunks_to_buffer:
                if chunk_index >= total_chunks:
                    continue
                if chunk_index in cached_chunks:
                    continue
                if chunk_index in downloading_chunks:
                    continue
                
                # Determine priority
                distance_from_current = abs(chunk_index - current_chunk)
                if distance_from_current <= 1:
                    priority = DownloadPriority.CRITICAL
                elif distance_from_current <= self._playback_session.min_buffer_chunks:
                    priority = DownloadPriority.HIGH
                else:
                    priority = DownloadPriority.NORMAL
                
                # Create and queue download task
                task = ChunkDownloadTask(
                    song_id=song_id,
                    chunk_index=chunk_index,
                    priority=priority,
                )
                self._download_manager.add_task(task)
                
                # Mark as downloading in our tracking
                with self._downloading_lock:
                    if song_id not in self._downloading_chunks:
                        self._downloading_chunks[song_id] = set()
                    self._downloading_chunks[song_id].add(chunk_index)
                
                with self._status_lock:
                    if song_id not in self._chunk_status:
                        self._chunk_status[song_id] = {}
                    self._chunk_status[song_id][chunk_index] = ChunkStatus.DOWNLOADING
                
                logger.info(f"Queued chunk for buffering: {song_id} [{chunk_index}] priority={priority.name}")
            
            # Clean up completed downloads from tracking
            self._cleanup_download_tracking(song_id)
            
        except Exception as e:
            logger.error(f"Failed to buffer chunks: {e}")
    
    def _cleanup_download_tracking(self, song_id: str) -> None:
        """Clean up download tracking for chunks that are now cached."""
        try:
            cached_chunks = set(self._get_cached_chunks(song_id))
            
            with self._downloading_lock:
                if song_id in self._downloading_chunks:
                    # Remove chunks that are now cached
                    self._downloading_chunks[song_id] = self._downloading_chunks[song_id] - cached_chunks
                    
                    # Clean up empty entries
                    if not self._downloading_chunks[song_id]:
                        del self._downloading_chunks[song_id]
            
            with self._status_lock:
                if song_id in self._chunk_status:
                    # Mark cached chunks as downloaded
                    for chunk_index in cached_chunks:
                        self._chunk_status[song_id][chunk_index] = ChunkStatus.DOWNLOADED
                        
        except Exception as e:
            logger.error(f"Failed to cleanup download tracking: {e}")
    
    def cleanup_cache(self) -> None:
        """Clean up old or excess cached chunks."""
        try:
            # Get total cache size
            total_size = self._get_total_cache_size()
            
            logger.info(f"Current cache size: {total_size / (1024*1024):.2f} MB")
            
            # If cache is too large, remove oldest chunks
            if total_size > self._cache_max_size_bytes:
                chunks_to_remove = self._get_chunks_to_remove(
                    total_size - self._cache_max_size_bytes
                )
                self._remove_chunks(chunks_to_remove)
                
                # Also update status tracking
                for chunk in chunks_to_remove:
                    chunk_index = self._get_chunk_index(chunk.start_ms)
                    with self._status_lock:
                        if chunk.song_id in self._chunk_status:
                            if chunk_index in self._chunk_status[chunk.song_id]:
                                del self._chunk_status[chunk.song_id][chunk_index]
                
        except Exception as e:
            logger.error(f"Failed to cleanup cache: {e}")
    
    def _get_total_cache_size(self) -> int:
        """Get the total size of all cached chunks."""
        try:
            total_size = 0
            for root, dirs, files in os.walk(CHUNKS_DIR):
                for file in files:
                    file_path = Path(root) / file
                    total_size += os.path.getsize(file_path)
            return total_size
        except Exception as e:
            logger.error(f"Failed to calculate cache size: {e}")
            return 0
    
    def _get_chunks_to_remove(self, target_size: int) -> List[CachedChunk]:
        """Get chunks to remove to reduce cache size by target_size."""
        try:
            db = next(get_userdb_session())
            
            # Get all chunks sorted by last_accessed (oldest first)
            chunks = db.query(CachedChunk).order_by(CachedChunk.last_accessed.asc()).all()
            
            chunks_to_remove = []
            current_size = 0
            
            for chunk in chunks:
                if os.path.exists(chunk.file_path):
                    file_size = os.path.getsize(chunk.file_path)
                    if current_size + file_size <= target_size:
                        chunks_to_remove.append(chunk)
                        current_size += file_size
                    else:
                        break
            
            return chunks_to_remove
            
        except Exception as e:
            logger.error(f"Failed to get chunks to remove: {e}")
            return []
    
    def _remove_chunks(self, chunks: List[CachedChunk]) -> None:
        """Remove chunks from filesystem and database."""
        try:
            db = next(get_userdb_session())
            
            for chunk in chunks:
                try:
                    # Remove file
                    if os.path.exists(chunk.file_path):
                        os.remove(chunk.file_path)
                    
                    # Remove from database
                    db.delete(chunk)
                    
                    logger.debug(f"Removed chunk: {chunk.song_id} [{chunk.start_ms}-{chunk.end_ms}]")
                except Exception as e:
                    logger.error(f"Failed to remove chunk: {e}")
            
            db.commit()
            
            logger.info(f"Removed {len(chunks)} chunks from cache")
            
        except Exception as e:
            logger.error(f"Failed to remove chunks: {e}")
    
    def cache_full_song(self, song_id: str) -> bool:
        """
        Download and cache the full song.
        
        Args:
            song_id: YouTube video ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get song duration
            stream_info = self.get_stream_info(song_id)
            
            if not stream_info or not stream_info.duration_ms:
                logger.error(f"Could not get stream info for: {song_id}")
                return False
            
            # Download all chunks
            total_chunks = stream_info.total_chunks
            for chunk_index in range(total_chunks):
                chunk_path = self.download_chunk(song_id, chunk_index)
                if not chunk_path:
                    logger.error(f"Failed to download chunk {chunk_index} for: {song_id}")
                    return False
            
            logger.info(f"Cached full song: {song_id} ({total_chunks} chunks)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache full song: {e}")
            return False
    
    def start_playback(self, song_id: str) -> bool:
        """
        Start playback for a song.
        
        Args:
            song_id: YouTube video ID
            
        Returns:
            True if playback started successfully
        """
        try:
            # Set the song in playback session
            self._playback_session.set_song(song_id)
            self._playback_session.set_playing(True)
            
            # Get stream info to know how many chunks we need
            stream_info = self.get_stream_info(song_id)
            if not stream_info:
                logger.error(f"Could not get stream info for playback: {song_id}")
                return False
            
            # Start buffering chunks
            self.buffer_chunks_for_song(song_id, stream_info.total_chunks)
            
            # Save playback state to database
            self._save_playback_state()
            
            logger.info(f"Started playback: {song_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start playback: {e}")
            return False
    
    def pause_playback(self) -> None:
        """Pause the current playback."""
        self._playback_session.set_playing(False)
        self._save_playback_state()
        logger.info("Playback paused")
    
    def resume_playback(self) -> None:
        """Resume the current playback."""
        self._playback_session.set_playing(True)
        
        # Continue buffering
        current_song = self._playback_session.current_song_id
        if current_song:
            stream_info = self.get_stream_info(current_song)
            if stream_info:
                self.buffer_chunks_for_song(current_song, stream_info.total_chunks)
        
        self._save_playback_state()
        logger.info("Playback resumed")
    
    def stop_playback(self) -> None:
        """Stop the current playback."""
        self._playback_session.set_playing(False)
        self._playback_session.current_song_id = None
        self._save_playback_state()
        logger.info("Playback stopped")
    
    def update_playback_position(self, position_ms: int) -> None:
        """
        Update the current playback position.
        
        Args:
            position_ms: Current position in milliseconds
        """
        self._playback_session.update_position(position_ms)
        self._save_playback_state()
        
        # Update buffering based on new position
        current_song = self._playback_session.current_song_id
        if current_song:
            stream_info = self.get_stream_info(current_song)
            if stream_info:
                self.buffer_chunks_for_song(current_song, stream_info.total_chunks)
    
    def _save_playback_state(self) -> None:
        """Save current playback state to database."""
        try:
            db = next(get_playdb_session())
            
            playback_info = self._playback_session.get_playback_info()
            
            playback_state = db.query(PlaybackState).first()
            
            if playback_state:
                playback_state.current_song_id = self._playback_session.current_song_id
                playback_state.current_time_ms = playback_info.current_position_ms
                playback_state.is_playing = playback_info.is_playing
                playback_state.volume = playback_info.volume
                playback_state.updated_at = datetime.utcnow()
            else:
                playback_state = PlaybackState(
                    current_song_id=self._playback_session.current_song_id,
                    current_time_ms=playback_info.current_position_ms,
                    is_playing=playback_info.is_playing,
                    volume=playback_info.volume,
                )
                db.add(playback_state)
            
            db.commit()
            logger.debug(f"Saved playback state: song={self._playback_session.current_song_id}, position={playback_info.current_position_ms}ms, playing={playback_info.is_playing}")
            
        except Exception as e:
            logger.error(f"Failed to save playback state: {e}")
    
    def get_playback_state(self) -> Dict[str, Any]:
        """
        Get the current playback state.
        
        Returns:
            Dictionary with playback state information
        """
        try:
            db = next(get_playdb_session())
            playback_state = db.query(PlaybackState).first()
            
            if playback_state:
                return {
                    "current_song_id": playback_state.current_song_id,
                    "current_time_ms": playback_state.current_time_ms,
                    "is_playing": playback_state.is_playing,
                    "volume": playback_state.volume,
                    "repeat_mode": playback_state.repeat_mode,
                    "shuffle": playback_state.shuffle,
                    "updated_at": playback_state.updated_at.isoformat() if playback_state.updated_at else None,
                }
            else:
                return {
                    "current_song_id": None,
                    "current_time_ms": 0,
                    "is_playing": False,
                    "volume": 1.0,
                    "repeat_mode": RepeatMode.NONE.value,
                    "shuffle": False,
                }
                
        except Exception as e:
            logger.error(f"Failed to get playback state: {e}")
            return {
                "current_song_id": None,
                "current_time_ms": 0,
                "is_playing": False,
                "volume": 1.0,
                "repeat_mode": RepeatMode.NONE.value,
                "shuffle": False,
            }
    
    def get_song_chunks_status(self, song_id: str) -> Dict[str, Any]:
        """
        Get the status of all chunks for a song.
        
        Returns a dictionary with:
        - total_chunks: Total number of chunks
        - chunk_status: Dictionary mapping chunk index to status string
        - cached_count: Number of cached chunks
        - downloading_count: Number of chunks currently downloading
        """
        try:
            stream_info = self.get_stream_info(song_id)
            
            if not stream_info:
                return {
                    "total_chunks": 0,
                    "chunk_status": {},
                    "cached_count": 0,
                    "downloading_count": 0,
                }
            
            chunk_status = self.get_chunk_status(song_id, stream_info.total_chunks)
            downloading_chunks = self.get_downloading_chunks(song_id)
            
            # Convert status enum to string
            status_dict = {idx: status.value for idx, status in chunk_status.items()}
            
            # Count cached chunks
            cached_count = len([s for s in status_dict.values() if s == ChunkStatus.DOWNLOADED.value])
            downloading_count = len(downloading_chunks)
            
            return {
                "total_chunks": stream_info.total_chunks,
                "chunk_status": status_dict,
                "cached_count": cached_count,
                "downloading_count": downloading_count,
                "duration_ms": stream_info.duration_ms,
            }
            
        except Exception as e:
            logger.error(f"Failed to get song chunks status: {e}")
            return {
                "total_chunks": 0,
                "chunk_status": {},
                "cached_count": 0,
                "downloading_count": 0,
            }
    
    def get_current_chunk_index(self) -> int:
        """Get the current chunk index from playback session."""
        return self._playback_session.get_current_chunk_index()
    
    def get_current_song_id(self) -> Optional[str]:
        """Get the current song ID from playback session."""
        return self._playback_session.current_song_id
    
    def shutdown(self) -> None:
        """Shutdown the streaming service."""
        logger.info("Shutting down StreamingService...")
        self._download_manager.stop()
        logger.info("StreamingService shutdown complete")
