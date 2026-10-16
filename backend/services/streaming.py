"""
Streaming Service
================
Service layer for audio streaming from YouTube using yt-dlp.

This service provides:
- Chunk downloading from YouTube
- Format and quality selection
- Chunk caching and management
- Streaming endpoint support
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, BinaryIO
from dataclasses import dataclass, asdict
import hashlib
import shutil

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
)
from backend.database.session import get_userdb_session
from backend.database.models import Song, CachedChunk
from backend.utils.logger import get_logger

logger = get_logger(__name__)


# Singleton instance
_streaming_service_instance = None


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


@dataclass
class ChunkInfo:
    """Information about a cached audio chunk."""
    song_id: str
    start_ms: int
    end_ms: int
    file_path: Path
    size_bytes: int
    chunk_index: int
    
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
    
    def __post_init__(self):
        if self.cached_chunks is None:
            self.cached_chunks = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


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
        
        logger.info(f"StreamingService initialized: quality={AUDIO_QUALITY}, chunk_size={CHUNK_SIZE_SEC}s")
    
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
        
        # Create hash of song_id and chunk_index for uniqueness
        chunk_hash = hashlib.md5(f"{song_id}_{chunk_index}".encode()).hexdigest()
        
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
                # total_chunks = ceil(duration_ms / chunk_size_ms)
                # Using integer arithmetic: (duration + chunk_size - 1) // chunk_size
                total_chunks = (duration_ms + self._chunk_size_ms - 1) // self._chunk_size_ms
            else:
                total_chunks = 0
            
            # Get cached chunks
            cached_chunks = self._get_cached_chunks(song_id)
            
            return StreamInfo(
                song_id=song_id,
                title=song_metadata.title if song_metadata else song_id,
                duration_ms=duration_ms,
                total_chunks=total_chunks,
                cached_chunks=cached_chunks,
            )
            
        except Exception as e:
            logger.error(f"Failed to get stream info: {e}")
            return None
    
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
    
    def download_chunk(self, song_id: str, chunk_index: int, force: bool = False) -> Optional[Path]:
        """
        Download a specific chunk of a song.
        
        Args:
            song_id: YouTube video ID
            chunk_index: Chunk index (0-based)
            force: Force re-download even if cached
            
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
                return existing_chunk
            
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
            
            if not success:
                logger.error(f"Failed to download chunk: {song_id} [{chunk_index}]")
                return None
            
            # Save chunk metadata to database
            self._save_chunk_metadata(song_id, start_ms, end_ms, output_path)
            
            logger.info(f"Chunk downloaded: {song_id} [{chunk_index}] -> {output_path}")
            return output_path
            
        except Exception as e:
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
