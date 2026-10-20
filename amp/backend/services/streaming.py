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
import requests
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
    LOGS_DIR,
)

from backend.database.session import get_userdb_session, get_playdb_session
from backend.services.auth import get_auth_service
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
        "format": "bestaudio[acodec=opus][abr<=96]/best",
        "bitrate": 96,
        "file_ext": "opus",
    },
    "medium": {
        "format": "bestaudio[acodec=opus][abr<=128]/best",
        "bitrate": 128,
        "file_ext": "opus",
    },
    "high": {
        "format": "bestaudio[acodec=opus][abr<=192]/best",
        "bitrate": 192,
        "file_ext": "opus",
    },
    "best": {
        "format": "bestaudio[acodec=opus]/best",
        "bitrate": 320,
        "file_ext": "opus",
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
        # Initialize log buffer for debugging (in-memory + file)
        self._streaming_logs: List[str] = []
        self._max_logs = 200
        # Persistent streaming log file
        self._stream_log_path = Path(LOGS_DIR) / "streaming.log"
        Path(LOGS_DIR).mkdir(parents=True, exist_ok=True)
        self._stream_log_lock = threading.Lock()
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

        # Cache stream info per song (avoid repeated YouTube API / yt-dlp calls)
        self._stream_info_cache: Dict[str, 'StreamInfo'] = {}
        self._stream_info_lock = threading.Lock()

        # Cache direct stream URLs per song (avoid repeated yt-dlp calls)
        self._stream_urls: Dict[str, str] = {}
        self._stream_urls_lock = threading.Lock()

        # Cache content lengths per song
        self._stream_sizes: Dict[str, int] = {}

        # Cache chunk byte ranges per song: song_id -> list of (start_byte, end_byte)
        self._chunk_byte_ranges: Dict[str, List[Tuple[int, int]]] = {}

        # Initialize chunk cache tracking
        self._initialize_chunk_cache()
        
        logger.info(f"StreamingService initialized: quality={AUDIO_QUALITY}, chunk_size={CHUNK_SIZE_SEC}s")
    
    def _log_streaming(self, msg: str, level: str = "INFO") -> None:
        """Log to both in-memory buffer and persistent file."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        entry = f"[{ts}] [{level}] {msg}"
        # In-memory buffer
        self._streaming_logs.append(entry)
        if len(self._streaming_logs) > self._max_logs:
            self._streaming_logs = self._streaming_logs[-self._max_logs:]
        # Persistent file
        try:
            with self._stream_log_lock:
                with open(self._stream_log_path, "a", encoding="utf-8") as f:
                    f.write(entry + "\n")
        except Exception:
            pass
        # Also log via standard logger
        if level == "ERROR":
            logger.error(msg)
        elif level == "WARNING":
            logger.warning(msg)
        else:
            logger.info(msg)

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
            
            db.close()
        except Exception as e:
            logger.error(f"Failed to initialize chunk cache: {e}")
    
    def _get_yt_dlp_cookie_args(self) -> list:
        """
        Get yt-dlp arguments for authentication using cookies from the auth service.
        Returns a list of arguments to pass to yt-dlp (e.g., ['--cookies', '/path/to/file']).
        Returns empty list if not authenticated.
        """
        try:
            auth = get_auth_service()
            if not auth.is_authenticated:
                return []
            
            cookies = auth.get_cookies_dict()
            if not cookies:
                return []
            
            # Write cookies to a temporary Netscape-format file
            import tempfile
            cookie_file = tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.txt',
                prefix='amp_cookies_',
                delete=False,
            )
            cookie_file.write("# Netscape HTTP Cookie File\n")
            cookie_file.write("# This file was generated by AMP for yt-dlp authentication\n")
            
            for name, value in cookies.items():
                # Netscape format: domain, include_subdomains, path, secure, expiry, name, value
                cookie_file.write(".youtube.com\tTRUE\t/\tTRUE\t0\t" + name + "\t" + value + "\n")
                cookie_file.write(".music.youtube.com\tTRUE\t/\tTRUE\t0\t" + name + "\t" + value + "\n")
            
            cookie_file.close()
            logger.debug(f"Wrote {len(cookies)} cookies to {cookie_file.name}")
            
            return ['--cookies', cookie_file.name]
            
        except Exception as e:
            logger.warning(f"Failed to get cookie args for yt-dlp: {e}")
            return []

    def _get_ffmpeg_path(self) -> Optional[str]:
        """Get the path to ffmpeg executable. Checks tools directory and PATH."""
        import shutil

        # Check tools directory (downloaded static build)
        tools_ffmpeg = BASE_DIR / "tools" / "ffmpeg-master-latest-win64-gpl" / "bin" / "ffmpeg.exe"
        if tools_ffmpeg.exists():
            return str(tools_ffmpeg)

        tools_ffmpeg_alt = BASE_DIR / "tools" / "ffmpeg-master-latest-win64-gpl" / "bin" / "ffmpeg"
        if tools_ffmpeg_alt.exists():
            return str(tools_ffmpeg_alt)

        # Check if ffmpeg is in PATH
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            return ffmpeg

        return None

    def _get_yt_dlp_path(self) -> str:
        """Get the path to yt-dlp executable. Prefers venv installation."""
        import shutil
        import sys
        
        # Prefer venv's yt-dlp (has EJS components installed)
        venv_scripts = Path(sys.executable).parent
        venv_yt_dlp = venv_scripts / "yt-dlp.exe"
        if venv_yt_dlp.exists():
            return str(venv_yt_dlp)
        
        venv_bin_yt_dlp = venv_scripts / "yt-dlp"
        if venv_bin_yt_dlp.exists():
            return str(venv_bin_yt_dlp)
        
        # Check if yt-dlp is in PATH
        yt_dlp = shutil.which("yt-dlp")
        if yt_dlp:
            return yt_dlp
        
        # Check common locations
        common_paths = [
            str(BASE_DIR / "venv" / "Scripts" / "yt-dlp.exe"),
            str(BASE_DIR / "venv" / "bin" / "yt-dlp"),
            "yt-dlp",
            "yt-dlp.exe",
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
        
        # Use opus extension for Phase 3 (no ffmpeg required)
        file_ext = "opus"
        
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
    
    def _get_direct_audio_url(self, song_id: str) -> Optional[str]:
        """
        Get the direct URL for an audio stream using yt-dlp.
        Returns the URL for the best opus audio format available.
        """
        try:
            yt_dlp = self._get_yt_dlp_path()
            url = self.get_song_url(song_id)
            
            # Try opus audio formats first (251, 249 are webm with opus)
            for format_id in ['251', '249', '140', '139']:
                cmd = [
                    yt_dlp,
                    '-g',
                    '--format', format_id,
                    '--quiet',
                    '--no-warnings',
                    '--js-runtimes', 'node',
                ]
                cmd.extend(self._get_yt_dlp_cookie_args())
                cmd.append(url)
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                
                if result.returncode == 0 and result.stdout:
                    direct_url = result.stdout.strip()
                    if direct_url and 'http' in direct_url:
                        logger.debug(f"Got direct audio URL (format {format_id}): {direct_url[:100]}...")
                        return direct_url
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get direct audio URL: {e}")
            return None

    def _get_cdn_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Build headers for YouTube CDN requests, including auth cookies and User-Agent."""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        try:
            from backend.services.auth import get_auth_service
            auth = get_auth_service()
            cookie_header = auth.get_cookie_header()
            if cookie_header:
                headers['Cookie'] = cookie_header
        except Exception as e:
            logger.debug(f"Could not get cookies for CDN request: {e}")
        if extra:
            headers.update(extra)
        return headers

    def _parse_url_clen(self, url: str) -> Optional[int]:
        """Extract content length (clen) from the stream URL query parameters."""
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = parse_qs(urlparse(url).query)
            clen = parsed.get("clen", [None])[0]
            if clen and clen.isdigit():
                return int(clen)
        except Exception:
            pass
        return None

    def _parse_url_metadata(self, url: str) -> Dict[str, str]:
        """Extract useful metadata from the stream URL."""
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = parse_qs(urlparse(url).query)
            return {
                "client": parsed.get("c", ["?"])[0],
                "clen": parsed.get("clen", ["?"])[0],
                "dur": parsed.get("dur", ["?"])[0],
                "itag": parsed.get("itag", ["?"])[0],
                "mime": parsed.get("mime", ["?"])[0],
                "expire": parsed.get("expire", ["?"])[0],
            }
        except Exception:
            return {}

    def _refresh_stream_url(self, song_id: str) -> Optional[str]:
        """Invalidate cached URL/size/byte-ranges and fetch a fresh stream URL."""
        with self._stream_urls_lock:
            self._stream_urls.pop(song_id, None)
        self._stream_sizes.pop(song_id, None)
        self._chunk_byte_ranges.pop(song_id, None)
        self._log_streaming(f"Refreshing stream URL for: {song_id}")
        return self._get_stream_url_cached(song_id)

    def _get_url_content_length(self, url: str) -> Optional[int]:
        """
        Get the content length of a URL using multiple strategies.

        Strategy 1: HEAD request (fastest, but YouTube CDN sometimes omits Content-Length)
        Strategy 2: GET with Range: bytes=0-0, parse Content-Range header (most reliable for CDNs)
        Strategy 3: Return None (caller will fall back to yt-dlp --get-filesize or estimation)
        """
        cdn_headers = self._get_cdn_headers()

        # Strategy 1: HEAD request
        try:
            response = requests.head(url, headers=cdn_headers, timeout=10, allow_redirects=True)
            if response.status_code in (200, 206):
                content_length = response.headers.get('content-length')
                if content_length:
                    logger.debug(f"Content length from HEAD: {content_length}")
                    return int(content_length)
        except Exception as e:
            logger.debug(f"HEAD request failed: {e}")

        # Strategy 2: GET with Range: bytes=0-0, parse Content-Range
        try:
            range_headers = self._get_cdn_headers({'Range': 'bytes=0-0'})
            response = requests.get(
                url,
                headers=range_headers,
                stream=True,
                timeout=15,
                allow_redirects=True,
            )
            # Content-Range: bytes 0-0/1234567
            content_range = response.headers.get('content-range')
            if content_range and '/' in content_range:
                total = content_range.split('/')[-1]
                if total.isdigit():
                    logger.debug(f"Content length from Content-Range: {total}")
                    response.close()
                    return int(total)
            # Also check content-length on the 206 response
            content_length = response.headers.get('content-length')
            if content_length and response.status_code == 200:
                logger.debug(f"Content length from GET: {content_length}")
                response.close()
                return int(content_length)
            response.close()
        except Exception as e:
            logger.debug(f"Range probe failed: {e}")

        self._log_streaming(f"Could not determine content length for URL: {url[:80]}...", "WARNING")
        return None

    def _get_filesize_with_yt_dlp(self, song_id: str) -> Optional[int]:
        """Get the file size using yt-dlp --get-filesize as a fallback."""
        try:
            yt_dlp = self._get_yt_dlp_path()
            url = self.get_song_url(song_id)

            cmd = [
                yt_dlp,
                '--quiet',
                '--no-warnings',
                '--no-progress',
                '--js-runtimes', 'node',
                '--get-filesize',
                '--format', 'bestaudio[acodec=opus][abr>=96]/bestaudio[abr>=96]',
                url,
            ]
            cmd.extend(self._get_yt_dlp_cookie_args())

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                size = int(result.stdout.strip())
                logger.debug(f"File size from yt-dlp: {size}")
                return size
            return None
        except Exception as e:
            logger.error(f"Failed to get file size with yt-dlp: {e}")
            return None

    def _download_byte_range(
        self,
        url: str,
        output_path: Path,
        start_byte: int,
        end_byte: Optional[int] = None,
    ) -> Tuple[bool, int]:
        """
        Download a specific byte range from a URL using HTTP Range requests.
        This allows chunk-by-chunk downloading without ffmpeg.
        
        Returns:
            Tuple of (success: bool, http_status_code: int)
        """
        try:
            os.makedirs(output_path.parent, exist_ok=True)
            
            if end_byte is not None:
                range_header = f'bytes={start_byte}-{end_byte}'
            else:
                range_header = f'bytes={start_byte}-'
            
            headers = self._get_cdn_headers({'Range': range_header})
            
            logger.debug(f"Downloading byte range {range_header} from {url[:50]}...")
            
            response = requests.get(
                url,
                headers=headers,
                stream=True,
                timeout=30,
            )
            
            if response.status_code not in [200, 206]:
                self._log_streaming(f"HTTP {response.status_code} for byte range {range_header} from {url[:60]}...", "ERROR")
                return False, response.status_code
            self._log_streaming(f"HTTP {response.status_code} for byte range {range_header}")
            
            with open(output_path, 'wb') as f:
                for chunk_data in response.iter_content(chunk_size=8192):
                    if chunk_data:
                        f.write(chunk_data)
            
            if output_path.exists() and output_path.stat().st_size > 0:
                self._log_streaming(f"Byte range saved: {output_path.name} ({output_path.stat().st_size} bytes)")
                return True, response.status_code
            else:
                logger.error(f"Downloaded file is empty: {output_path}")
                return False, response.status_code
                
        except Exception as e:
            logger.error(f"Failed to download byte range: {e}")
            return False, 0


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
                "--js-runtimes", "node",
                "--output", str(output_path),
            ]
            
            # Add authentication cookies if available
            cookie_args = self._get_yt_dlp_cookie_args()
            if cookie_args:
                cmd.extend(cookie_args)
                logger.debug("Using authentication cookies for yt-dlp")
            
            # Add format - use bestaudio without ffmpeg requirement
            # Opus format doesn't require ffmpeg for most cases
            if format_str:
                cmd.extend(["--format", format_str])
            else:
                # Use opus format which doesn't require ffmpeg for extraction
                cmd.extend(["--format", "bestaudio[acodec=opus][abr>=96]/bestaudio[abr>=96]"])
            
            # Prevent any postprocessing that requires ffmpeg
            cmd.extend([
                "--no-post-overwrites",
                "--no-mtime",
            ])
            
            # Don't use --extract-audio since we're using audio-only format
            # Don't specify --audio-format to avoid ffmpeg conversion
            
            # Add URL - for now, don't use partial downloads which require ffmpeg
            # Instead, we'll download the full audio file and manage chunks differently
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
                # Log full command for debugging
                logger.error(f"yt-dlp command failed: {" ".join(cmd)}")
                logger.error(f"yt-dlp stdout: {result.stdout}")
                # Add to log buffer
                self._streaming_logs.append(f"yt-dlp failed for {url}: {result.stderr[:200]}")
                if len(self._streaming_logs) > self._max_logs:
                    self._streaming_logs = self._streaming_logs[-self._max_logs:]
                logger.error(f"yt-dlp failed: {result.stderr}")
                return False
            
            # Check if file was created
            if not output_path.exists():
                logger.error(f"Output file not created: {output_path}")
                return False
            
            self._streaming_logs.append(f"Successfully downloaded: {url}")
            if len(self._streaming_logs) > self._max_logs:
                self._streaming_logs = self._streaming_logs[-self._max_logs:]
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
        # Check cache first - stream info doesn't change for a given song
        with self._stream_info_lock:
            cached = self._stream_info_cache.get(song_id)
            if cached is not None:
                # Refresh dynamic fields (cached_chunks, downloading_chunks, chunk_status)
                cached.cached_chunks = self._get_cached_chunks(song_id)
                cached.downloading_chunks = self.get_downloading_chunks(song_id)
                return cached

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
            
            info = StreamInfo(
                song_id=song_id,
                title=song_metadata.title if song_metadata else song_id,
                duration_ms=duration_ms,
                total_chunks=total_chunks,
                cached_chunks=cached_chunks,
                downloading_chunks=downloading_chunks,
            )
            # Cache the result (duration and total_chunks never change)
            with self._stream_info_lock:
                self._stream_info_cache[song_id] = info
            return info
            
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
                "--js-runtimes", "node",
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
                # Duration can be in format HH:MM:SS or MM:SS or SS or just a float string
                duration_str = result.stdout.strip()
                
                # Try to parse as float seconds first (some versions return just seconds)
                try:
                    duration_sec = float(duration_str)
                    return int(duration_sec * 1000)
                except ValueError:
                    pass  # Try parsing as time format next
                
                # Parse as time format
                try:
                    parts = duration_str.split(':')
                    if len(parts) == 1:
                        # Just seconds (as string, not float)
                        duration_sec = float(parts[0])
                    elif len(parts) == 2:
                        # MM:SS
                        minutes = float(parts[0])
                        seconds = float(parts[1])
                        duration_sec = minutes * 60 + seconds
                    elif len(parts) == 3:
                        # HH:MM:SS
                        hours = float(parts[0])
                        minutes = float(parts[1])
                        seconds = float(parts[2])
                        duration_sec = hours * 3600 + minutes * 60 + seconds
                    else:
                        duration_sec = 0
                    
                    return int(duration_sec * 1000)
                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse duration string '{duration_str}': {e}")
                    return None
            
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
            
            db.close()
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
            
            db.close()
        except Exception as e:
            logger.error(f"Failed to get chunk: {e}")
            return None
    
    def _get_stream_url_cached(self, song_id: str) -> Optional[str]:
        """Get the direct stream URL, using cache if available."""
        with self._stream_urls_lock:
            if song_id in self._stream_urls:
                return self._stream_urls[song_id]

        url = self._get_direct_audio_url(song_id)
        if url:
            meta = self._parse_url_metadata(url)
            self._log_streaming(
                f"Stream URL cached: {song_id} | client={meta.get("client","?")} "
                f"clen={meta.get("clen","?")} dur={meta.get("dur","?")}s "
                f"itag={meta.get("itag","?")} expire={meta.get("expire","?")}"
            )
            with self._stream_urls_lock:
                self._stream_urls[song_id] = url
        return url

    def _get_stream_size_cached(self, song_id: str, url: str) -> Optional[int]:
        """
        Get the content length of the stream, using cache if available.

        Fallback chain:
        1. Cache (instant)
        2. HTTP HEAD / Range probe on the direct URL
        3. yt-dlp --get-filesize
        4. Estimate from bitrate x duration (128kbps default)
        """
        if song_id in self._stream_sizes:
            return self._stream_sizes[song_id]

        # Strategy 0: Parse clen from URL query params (instant, no HTTP request)
        size = self._parse_url_clen(url)
        if size:
            self._log_streaming(f"Content length from URL clen param: {size} bytes for {song_id}")
            self._stream_sizes[song_id] = size
            return size

        # Strategy 1: HTTP content length
        size = self._get_url_content_length(url)
        if size:
            self._stream_sizes[song_id] = size
            return size

        # Strategy 2: yt-dlp --get-filesize
        logger.info(f"HTTP content length failed, trying yt-dlp --get-filesize for {song_id}")
        size = self._get_filesize_with_yt_dlp(song_id)
        if size:
            self._stream_sizes[song_id] = size
            return size

        # Strategy 3: Estimate from bitrate x duration
        logger.info(f"yt-dlp filesize failed, estimating from bitrate for {song_id}")
        stream_info = self.get_stream_info(song_id)
        if stream_info and stream_info.duration_ms:
            # Estimate at 160kbps (opus webm format 251)
            estimated_bitrate = 160 * 1000  # bits per second
            estimated_size = int(estimated_bitrate / 8 * (stream_info.duration_ms / 1000))
            # Add 10% overhead for container/headers
            estimated_size = int(estimated_size * 1.1)
            logger.info(f"Estimated stream size: {estimated_size} bytes ({estimated_size/1024/1024:.2f} MB)")
            self._stream_sizes[song_id] = estimated_size
            return estimated_size

        logger.error(f"All size detection strategies failed for {song_id}")
        return None

    def _get_chunk_byte_range(self, song_id: str, chunk_index: int) -> Optional[Tuple[int, int]]:
        """
        Calculate the byte range for a chunk based on stream content length and duration.

        Uses proportional calculation: chunk_bytes = total_bytes * (chunk_duration / total_duration)
        This ensures each chunk covers approximately CHUNK_SIZE_SEC seconds of audio.

        Returns:
            Tuple of (start_byte, end_byte) inclusive, or None if cannot calculate
        """
        # Check cache first
        if song_id in self._chunk_byte_ranges:
            ranges = self._chunk_byte_ranges[song_id]
            if 0 <= chunk_index < len(ranges):
                return ranges[chunk_index]
            return None

        # Get stream URL and content length
        url = self._get_stream_url_cached(song_id)
        if not url:
            logger.error(f"Cannot calculate byte range: no stream URL for {song_id}")
            return None

        content_length = self._get_stream_size_cached(song_id, url)
        if not content_length:
            logger.error(f"Cannot calculate byte range: no content length for {song_id}")
            return None

        # Get duration
        stream_info = self.get_stream_info(song_id)
        if not stream_info or not stream_info.duration_ms:
            logger.error(f"Cannot calculate byte range: no duration for {song_id}")
            return None

        duration_ms = stream_info.duration_ms
        total_chunks = stream_info.total_chunks

        # Calculate bytes per chunk proportionally
        bytes_per_ms = content_length / duration_ms
        chunk_size_bytes = int(bytes_per_ms * self._chunk_size_ms)

        # Calculate byte ranges for all chunks
        ranges = []
        for i in range(total_chunks):
            start_byte = i * chunk_size_bytes
            if i == total_chunks - 1:
                # Last chunk goes to end of file
                end_byte = content_length - 1
            else:
                end_byte = (i + 1) * chunk_size_bytes - 1
            ranges.append((start_byte, end_byte))

        # Cache the ranges
        self._chunk_byte_ranges[song_id] = ranges

        if 0 <= chunk_index < len(ranges):
            return ranges[chunk_index]
        return None

    def _get_chunk_byte_ranges(self, song_id: str) -> Optional[List[Tuple[int, int]]]:
        """Get all chunk byte ranges for a song. Calculates and caches if needed."""
        if song_id in self._chunk_byte_ranges:
            return self._chunk_byte_ranges[song_id]
        # Trigger calculation by getting range for chunk 0
        self._get_chunk_byte_range(song_id, 0)
        return self._chunk_byte_ranges.get(song_id)

    def download_chunk(self, song_id: str, chunk_index: int, force: bool = False, mark_downloading: bool = True) -> Optional[Path]:
        """
        Download a specific chunk of a song using HTTP Range requests.

        Strategy: Get the direct stream URL via yt-dlp (metadata only, fast),
        then download individual byte ranges using HTTP Range headers.
        Each chunk is ~10 seconds of audio (~160KB at 128kbps) and downloads
        independently - no full song download, no ffmpeg required.

        Args:
            song_id: YouTube video ID
            chunk_index: Chunk index (0-based)
            force: Force re-download even if cached
            mark_downloading: Whether to mark chunk as downloading in status

        Returns:
            Path to the downloaded chunk file or None if failed
        """
        try:
            # Calculate start and end ms for this chunk
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

            self._log_streaming(f"Starting chunk download: {song_id} [{chunk_index}] ({start_ms}-{end_ms}ms)")

            # Get the direct stream URL (cached after first call)
            stream_url = self._get_stream_url_cached(song_id)
            if not stream_url:
                self._log_streaming(f"Failed to get stream URL for: {song_id}", "ERROR")
                raise RuntimeError(f"No stream URL for {song_id}")

            # Calculate byte range for this chunk
            byte_range = self._get_chunk_byte_range(song_id, chunk_index)
            if not byte_range:
                logger.error(f"Failed to calculate byte range for: {song_id} [{chunk_index}]")
                raise RuntimeError(f"No byte range for {song_id} [{chunk_index}]")

            start_byte, end_byte = byte_range
            self._log_streaming(f"Byte range for chunk {chunk_index}: {start_byte}-{end_byte} ({end_byte - start_byte + 1} bytes)")

            # Generate output path
            output_path = self._generate_chunk_filename(song_id, chunk_index)

            # Download the byte range using HTTP Range request
            success, http_status = self._download_byte_range(stream_url, output_path, start_byte, end_byte)

            # On 403, the cached URL may be stale - refresh and retry once
            if not success and http_status == 403:
                self._log_streaming(f"HTTP 403 for {song_id} [{chunk_index}] - refreshing URL and retrying", "WARNING")
                fresh_url = self._refresh_stream_url(song_id)
                if fresh_url and fresh_url != stream_url:
                    # Recalculate byte range with fresh URL (clen may differ)
                    self._chunk_byte_ranges.pop(song_id, None)
                    byte_range = self._get_chunk_byte_range(song_id, chunk_index)
                    if byte_range:
                        start_byte, end_byte = byte_range
                        self._log_streaming(f"Retry byte range for chunk {chunk_index}: {start_byte}-{end_byte} ({end_byte - start_byte + 1} bytes)")
                        success, http_status = self._download_byte_range(fresh_url, output_path, start_byte, end_byte)
                else:
                    self._log_streaming(f"URL refresh did not produce a new URL for {song_id}", "WARNING")

            # Clean up downloading state
            if mark_downloading:
                with self._downloading_lock:
                    if song_id in self._downloading_chunks:
                        self._downloading_chunks[song_id].discard(chunk_index)

            if success and output_path.exists() and output_path.stat().st_size > 0:
                # Save metadata to database
                self._save_chunk_metadata(song_id, start_ms, end_ms, output_path)

                # Update status to downloaded
                with self._status_lock:
                    if song_id not in self._chunk_status:
                        self._chunk_status[song_id] = {}
                    self._chunk_status[song_id][chunk_index] = ChunkStatus.DOWNLOADED

                size = output_path.stat().st_size
                self._log_streaming(f"Chunk downloaded: {song_id} [{chunk_index}] -> {output_path.name} ({size} bytes, {start_ms}-{end_ms}ms)")
                return output_path
            else:
                # Mark as error
                with self._status_lock:
                    if song_id in self._chunk_status:
                        self._chunk_status[song_id][chunk_index] = ChunkStatus.ERROR

                self._log_streaming(f"Failed to download chunk: {song_id} [{chunk_index}] (bytes {start_byte}-{end_byte})", "ERROR")
                return None

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

    # =========================================================================
    # Chunk Splitting (ffmpeg-based)
    # =========================================================================

    def extract_chunk_from_full(self, song_id: str, chunk_index: int) -> Optional[Path]:
        """
        Extract a single chunk from the full song file using ffmpeg.

        This is the primary method for creating real chunk files.
        Downloads the full song if needed, then extracts the specific chunk.

        Args:
            song_id: YouTube video ID
            chunk_index: Chunk index (0-based, each chunk is CHUNK_SIZE_SEC seconds)

        Returns:
            Path to the chunk file or None if failed
        """
        try:
            ffmpeg = self._get_ffmpeg_path()
            if not ffmpeg:
                logger.error("ffmpeg not found - cannot extract chunk")
                return None

            # Get or download the full song
            full_path = self.get_full_song_path(song_id)
            if not full_path:
                logger.info(f"Full song not cached, downloading: {song_id}")
                full_path = self.download_full_song(song_id)

            if not full_path or not full_path.exists():
                logger.error(f"No full song available for: {song_id}")
                return None

            # Calculate start time for this chunk
            start_sec = chunk_index * CHUNK_SIZE_SEC

            # Generate output path
            output_path = self._generate_chunk_filename(song_id, chunk_index)

            # Check if chunk already exists
            if output_path.exists() and output_path.stat().st_size > 0:
                logger.debug(f"Chunk already exists: {output_path}")
                return output_path

            logger.info(f"Extracting chunk {chunk_index} from {full_path.name} (start={start_sec}s)")

            # Use ffmpeg to extract the chunk
            # -ss: start time, -t: duration, -c copy: no re-encoding (fast)
            cmd = [
                ffmpeg,
                '-y',  # Overwrite output
                '-ss', str(start_sec),  # Start time
                '-t', str(CHUNK_SIZE_SEC),  # Duration
                '-i', str(full_path),  # Input file
                '-c', 'copy',  # Copy codec (no re-encoding)
                '-avoid_negative_ts', 'make_zero',  # Fix timestamps
                str(output_path),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode != 0:
                # Retry with re-encoding if copy fails (some formats need it)
                logger.warning(f"ffmpeg copy failed, retrying with re-encode: {result.stderr[:200]}")
                cmd_reencode = [
                    ffmpeg,
                    '-y',
                    '-ss', str(start_sec),
                    '-t', str(CHUNK_SIZE_SEC),
                    '-i', str(full_path),
                    '-c:a', 'libopus',
                    '-b:a', '128k',
                    str(output_path),
                ]
                result = subprocess.run(cmd_reencode, capture_output=True, text=True, timeout=120)

                if result.returncode != 0:
                    logger.error(f"ffmpeg extraction failed: {result.stderr[:500]}")
                    return None

            if output_path.exists() and output_path.stat().st_size > 0:
                size = output_path.stat().st_size
                logger.info(f"Chunk extracted: {output_path.name} ({size} bytes)")

                # Save metadata
                start_ms = chunk_index * self._chunk_size_ms
                end_ms = start_ms + self._chunk_size_ms
                self._save_chunk_metadata(song_id, start_ms, end_ms, output_path)

                return output_path
            else:
                logger.error(f"Chunk file not created: {output_path}")
                return None

        except Exception as e:
            logger.error(f"Failed to extract chunk: {e}")
            return None

    def split_full_song_into_chunks(self, song_id: str, total_chunks: Optional[int] = None) -> int:
        """
        Split the full song into all chunk files using ffmpeg.

        Args:
            song_id: YouTube video ID
            total_chunks: Total number of chunks (calculated from duration if None)

        Returns:
            Number of chunks created
        """
        try:
            ffmpeg = self._get_ffmpeg_path()
            if not ffmpeg:
                logger.error("ffmpeg not found - cannot split song")
                return 0

            full_path = self.get_full_song_path(song_id)
            if not full_path:
                full_path = self.download_full_song(song_id)

            if not full_path or not full_path.exists():
                return 0

            # Get total chunks from duration if not provided
            if total_chunks is None:
                duration_ms = self._get_duration_with_yt_dlp(song_id)
                if duration_ms:
                    total_chunks = (duration_ms + self._chunk_size_ms - 1) // self._chunk_size_ms
                else:
                    total_chunks = 0

            if total_chunks <= 0:
                return 0

            logger.info(f"Splitting {full_path.name} into {total_chunks} chunks of {CHUNK_SIZE_SEC}s each")

            # Generate output pattern
            safe_id = re.sub(r"[^\w\-\.]", "_", song_id)
            output_pattern = str(CHUNKS_DIR / f"{safe_id}_%04d.opus")

            # Use ffmpeg segment muxer to split the file
            cmd = [
                ffmpeg,
                '-y',
                '-i', str(full_path),
                '-f', 'segment',
                '-segment_time', str(CHUNK_SIZE_SEC),
                '-c', 'copy',
                '-reset_timestamps', '1',
                output_pattern,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                logger.error(f"ffmpeg split failed: {result.stderr[:500]}")
                return 0

            # Count created chunks and save metadata
            created = 0
            for i in range(total_chunks):
                chunk_path = self._generate_chunk_filename(song_id, i)
                if chunk_path.exists() and chunk_path.stat().st_size > 0:
                    start_ms = i * self._chunk_size_ms
                    end_ms = start_ms + self._chunk_size_ms
                    self._save_chunk_metadata(song_id, start_ms, end_ms, chunk_path)

                    # Update status
                    with self._status_lock:
                        if song_id not in self._chunk_status:
                            self._chunk_status[song_id] = {}
                        self._chunk_status[song_id][i] = ChunkStatus.DOWNLOADED

                    created += 1

            logger.info(f"Split complete: {created}/{total_chunks} chunks created")
            return created

        except Exception as e:
            logger.error(f"Failed to split song into chunks: {e}")
            return 0

    # =========================================================================
    # Full Song Download (for direct playback)
    # =========================================================================

    def _generate_full_song_filename(self, song_id: str) -> Path:
        """Generate the filename for the full downloaded song."""
        safe_song_id = re.sub(r"[^\w\-\.]", "_", song_id)
        return CHUNKS_DIR / f"{safe_song_id}_full.opus"

    def download_full_song(self, song_id: str, force: bool = False) -> Optional[Path]:
        """
        Download the full song audio file for direct playback.

        This downloads the complete audio using yt-dlp, which is needed
        for actual playback (byte-range chunks are not independently playable).

        Args:
            song_id: YouTube video ID
            force: Force re-download even if cached

        Returns:
            Path to the downloaded file or None if failed
        """
        try:
            output_path = self._generate_full_song_filename(song_id)

            # Check if already downloaded
            if not force and output_path.exists() and output_path.stat().st_size > 0:
                logger.debug(f"Full song already cached: {song_id}")
                return output_path

            url = self.get_song_url(song_id)
            logger.info(f"Downloading full song: {song_id} -> {output_path}")

            self._streaming_logs.append(f"Downloading full song: {song_id}")
            if len(self._streaming_logs) > self._max_logs:
                self._streaming_logs = self._streaming_logs[-self._max_logs:]

            success = self._download_audio(url=url, output_path=output_path)

            if success and output_path.exists() and output_path.stat().st_size > 0:
                self._streaming_logs.append(f"Full song downloaded: {song_id} ({output_path.stat().st_size} bytes)")
                if len(self._streaming_logs) > self._max_logs:
                    self._streaming_logs = self._streaming_logs[-self._max_logs:]
                logger.info(f"Full song downloaded: {song_id} ({output_path.stat().st_size} bytes)")
                return output_path
            else:
                self._streaming_logs.append(f"Failed to download full song: {song_id}")
                if len(self._streaming_logs) > self._max_logs:
                    self._streaming_logs = self._streaming_logs[-self._max_logs:]
                logger.error(f"Failed to download full song: {song_id}")
                return None

        except Exception as e:
            logger.error(f"Failed to download full song: {e}")
            return None

    def generate_audio_stream(self, song_id: str):
        """
        Generator that yields audio data chunk by chunk for streaming playback.

        Each chunk is downloaded on-demand using HTTP Range requests if not cached.
        This allows instant playback start - only the first chunk needs to be
        downloaded before audio begins, subsequent chunks download progressively.

        Yields:
            bytes: Audio data from each chunk in sequence
        """
        try:
            stream_info = self.get_stream_info(song_id)
            if not stream_info or stream_info.total_chunks == 0:
                logger.error(f"Cannot stream audio: no stream info for {song_id}")
                return

            total_chunks = stream_info.total_chunks
            logger.info(f"Starting audio stream for {song_id}: {total_chunks} chunks")

            for chunk_index in range(total_chunks):
                # Get cached chunk or download it
                chunk_path = self.get_chunk(song_id, chunk_index)
                if not chunk_path:
                    logger.info(f"Chunk {chunk_index} not cached, downloading on-demand...")
                    chunk_path = self.download_chunk(song_id, chunk_index, mark_downloading=True)

                if not chunk_path or not chunk_path.exists():
                    logger.error(f"Failed to get chunk {chunk_index} for {song_id}, skipping")
                    continue

                # Read and yield the chunk data
                with open(chunk_path, "rb") as f:
                    while True:
                        data = f.read(65536)  # 64KB reads
                        if not data:
                            break
                        yield data

                logger.debug(f"Streamed chunk {chunk_index}/{total_chunks} for {song_id}")

            logger.info(f"Audio stream complete for {song_id}")

        except Exception as e:
            logger.error(f"Error in audio stream generator: {e}")

    def get_stream_content_type(self, song_id: str) -> str:
        """Get the MIME type for the audio stream."""
        # We request opus in webm format from yt-dlp
        return "audio/webm"

    def get_stream_total_bytes(self, song_id: str) -> Optional[int]:
        """Get the total byte size of the audio stream."""
        url = self._get_stream_url_cached(song_id)
        if not url:
            return None
        return self._get_stream_size_cached(song_id, url)

    def get_full_song_path(self, song_id: str) -> Optional[Path]:
        """
        Get the path to the full song file if it exists.

        Args:
            song_id: YouTube video ID

        Returns:
            Path to the file or None if not downloaded
        """
        output_path = self._generate_full_song_filename(song_id)
        if output_path.exists() and output_path.stat().st_size > 0:
            return output_path
        return None

    # =========================================================================
    # Chunk Metadata & Data Access
    # =========================================================================

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
        finally:
            db.close()

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

    # =========================================================================
    # Buffering & Download Management
    # =========================================================================

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

                self._log_streaming(f"Queued chunk for buffering: {song_id} [{chunk_index}] priority={priority.name}")

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

    # =========================================================================
    # Cache Management
    # =========================================================================

    def cleanup_cache(self) -> None:
        """Clean up old or excess cached chunks."""
        try:
            total_size = self._get_total_cache_size()
            logger.info(f"Current cache size: {total_size / (1024*1024):.2f} MB")
            if total_size > self._cache_max_size_bytes:
                chunks_to_remove = self._get_chunks_to_remove(
                    total_size - self._cache_max_size_bytes
                )
                self._remove_chunks(chunks_to_remove)
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
            db.close()
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
                    if os.path.exists(chunk.file_path):
                        os.remove(chunk.file_path)
                    db.delete(chunk)
                    logger.debug(f"Removed chunk: {chunk.song_id} [{chunk.start_ms}-{chunk.end_ms}]")
                except Exception as e:
                    logger.error(f"Failed to remove chunk: {e}")
            db.commit()
            db.close()
            logger.info(f"Removed {len(chunks)} chunks from cache")
        except Exception as e:
            logger.error(f"Failed to remove chunks: {e}")

    def cache_full_song(self, song_id: str) -> bool:
        """Download and cache the full song."""
        try:
            stream_info = self.get_stream_info(song_id)
            if not stream_info or not stream_info.duration_ms:
                logger.error(f"Could not get stream info for: {song_id}")
                return False
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

    # =========================================================================
    # Playback State Management
    # =========================================================================

    def start_playback(self, song_id: str) -> bool:
        """
        Start playback for a song.

        Args:
            song_id: YouTube video ID

        Returns:
            True if playback started successfully
        """
        try:
            self._playback_session.set_song(song_id)
            self._playback_session.set_playing(True)

            stream_info = self.get_stream_info(song_id)
            if not stream_info:
                logger.error(f"Could not get stream info for playback: {song_id}")
                return False

            self.buffer_chunks_for_song(song_id, stream_info.total_chunks)
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

        current_song = self._playback_session.current_song_id
        if current_song:
            stream_info = self.get_stream_info(current_song)
            if stream_info:
                self.buffer_chunks_for_song(current_song, stream_info.total_chunks)

    def seek_to_position(self, position_ms: int) -> Dict[str, Any]:
        """
        Seek to a new position. Cancels downloads for chunks before the new position
        and re-buffers chunks from the new position onwards.

        Args:
            position_ms: Target position in milliseconds

        Returns:
            Dict with seek result: new chunk index, cancelled chunks, buffered chunks
        """
        current_song = self._playback_session.current_song_id
        if not current_song:
            return {"error": "No active playback session"}

        # Calculate the target chunk index
        target_chunk = position_ms // self._chunk_size_ms

        # Get stream info
        stream_info = self.get_stream_info(current_song)
        if not stream_info:
            return {"error": f"Could not get stream info for {current_song}"}

        total_chunks = stream_info.total_chunks

        # Cancel downloads for chunks before the target position
        cancelled = []
        with self._downloading_lock:
            if current_song in self._downloading_chunks:
                to_cancel = {idx for idx in self._downloading_chunks[current_song] if idx < target_chunk}
                for idx in to_cancel:
                    self._downloading_chunks[current_song].discard(idx)
                    cancelled.append(idx)
                if not self._downloading_chunks[current_song]:
                    del self._downloading_chunks[current_song]

        # Reset status for cancelled chunks
        with self._status_lock:
            if current_song in self._chunk_status:
                for idx in cancelled:
                    if idx in self._chunk_status[current_song]:
                        self._chunk_status[current_song][idx] = ChunkStatus.NOT_DOWNLOADED

        # Also remove from DownloadManager's active downloads
        for idx in cancelled:
            self._download_manager.active_downloads.pop((current_song, idx), None)

        # Update playback position
        self._playback_session.update_position(position_ms)
        self._save_playback_state()

        # Re-buffer from the new position
        self.buffer_chunks_for_song(current_song, total_chunks)

        logger.info(f"Seeked to {position_ms}ms (chunk {target_chunk}/{total_chunks}), cancelled {len(cancelled)} downloads")

        return {
            "position_ms": position_ms,
            "chunk_index": target_chunk,
            "total_chunks": total_chunks,
            "cancelled_chunks": cancelled,
            "song_id": current_song,
        }

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
            db.close()
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
            db.close()

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
                    "duration_ms": None,
                }

            chunk_status = self.get_chunk_status(song_id, stream_info.total_chunks)
            downloading_chunks = self.get_downloading_chunks(song_id)

            status_dict = {idx: status.value for idx, status in chunk_status.items()}

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
                "duration_ms": None,
            }

    def get_current_chunk_index(self) -> int:
        """Get the current chunk index from playback session."""
        return self._playback_session.get_current_chunk_index()

    def get_current_song_id(self) -> Optional[str]:
        """Get the current song ID from playback session."""
        return self._playback_session.current_song_id

    # =========================================================================
    # Logging & Lifecycle
    # =========================================================================

    def get_streaming_logs(self) -> List[str]:
        """Get the streaming service log buffer."""
        return list(self._streaming_logs)

    def shutdown(self) -> None:
        """Shutdown the streaming service."""
        logger.info("Shutting down StreamingService...")
        self._download_manager.stop()
        logger.info("StreamingService shutdown complete")
