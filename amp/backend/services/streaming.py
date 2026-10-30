"""StreamingService — DASH segment streaming core.

Includes:
  - SegmentFetcher (yt-dlp -> manifest URL)
  - ManifestParser (uses utils/dash.py)
  - DownloadManager (PriorityQueue + ThreadPoolExecutor, 4 workers)
  - PlaybackSession (in-memory, epoch-based)
  - Cache management (LRU eviction, startup reconciliation)
  - Progressive fallback for non-DASH URLs
"""

from __future__ import annotations

import datetime as dt
import enum
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, PriorityQueue
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple

import requests

from backend.config import settings
from backend.database.models import Segment
from backend.database.session import session_scope
from backend.services.auth import get_auth_service
from backend.utils.dash import (
    StreamInfo,
    SegmentInfo as DashSegmentInfo,
    build_virtual_layout,
    map_range_to_segments,
    parse_mpd,
    position_ms_to_segment_index,
)
from backend.utils.logger import get_logger

logger = get_logger("backend.services.streaming")

# P13: song_id validation
SONG_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def validate_song_id(song_id: str) -> str:
    if not SONG_ID_RE.match(song_id):
        raise ValueError(f"Invalid song_id: {song_id!r}")
    return song_id


def build_ydl_opts(player_client: Optional[str], fmt: Optional[str], cookie_file: Optional[str]) -> Dict[str, Any]:
    """Build yt-dlp options with the shapes yt-dlp actually honours.

    - js_runtimes is a top-level {runtime: {config}} dict (P2), not an extractor arg.
    - extractor_args is {extractor: {key: [values]}} — a plain list is silently ignored.
    - player_client=None keeps yt-dlp's default client selection.
    """
    opts: Dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "socket_timeout": 15,
        "js_runtimes": {"node": {}},
    }
    if player_client:
        opts["extractor_args"] = {"youtube": {"player_client": [player_client]}}
    if fmt:
        opts["format"] = fmt
    if cookie_file:
        opts["cookiefile"] = cookie_file
    return opts


# Some clients (e.g. TVHTML5) return URLs that 403 until a few seconds after
# extraction; yt-dlp exposes this as the format's available_at timestamp.
MAX_AVAILABLE_AT_WAIT_S = 30


def _wait_until_available(fmt: Dict[str, Any], song_id: str) -> None:
    """Sleep until the format's URL is live (yt-dlp's available_at), capped."""
    available_at = fmt.get("available_at")
    if not available_at:
        return
    delay = available_at - time.time()
    if delay > 0:
        delay = min(delay, MAX_AVAILABLE_AT_WAIT_S)
        logger.info("Stream URL for %s not live yet, waiting %.1fs (available_at)", song_id, delay)
        time.sleep(delay)


def log_extraction_dependencies() -> None:
    """Log whether yt-dlp's JS challenge solver prerequisites are present (P2)."""
    import importlib.util
    import shutil

    node = shutil.which("node")
    if node:
        logger.info("JS runtime: node found at %s", node)
    else:
        logger.warning("JS runtime: node NOT found on PATH — yt-dlp cannot solve YouTube JS challenges")

    if importlib.util.find_spec("yt_dlp_ejs") is not None:
        logger.info("yt_dlp_ejs: importable")
    else:
        logger.warning('yt_dlp_ejs: NOT importable — install with: pip install -U "yt-dlp[default]"')


# ---------------------------------------------------------------------------
# Enums & data types
# ---------------------------------------------------------------------------


class SegmentStatus(str, enum.Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    ERROR = "error"


class Priority(int, enum.Enum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass
class SegmentTask:
    """A unit of work for the DownloadManager."""
    song_id: str
    index: int          # -1 = init segment
    priority: Priority
    epoch: int
    seq: int = 0        # tiebreaker for PriorityQueue

    def __lt__(self, other: "SegmentTask") -> bool:
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.seq < other.seq


@dataclass
class PlaybackInfo:
    song_id: str = ""
    current_segment_index: int = 0
    position_ms: int = 0
    is_playing: bool = False
    volume: float = 1.0
    epoch: int = 0
    last_updated: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "song_id": self.song_id,
            "current_segment_index": self.current_segment_index,
            "position_ms": self.position_ms,
            "is_playing": self.is_playing,
            "volume": self.volume,
            "epoch": self.epoch,
            "last_updated": self.last_updated,
        }


# ---------------------------------------------------------------------------
# Bounded in-memory cache (P19)
# ---------------------------------------------------------------------------


class BoundedDict:
    """A dict with a max size; evicts oldest (insertion order) when full."""

    def __init__(self, maxsize: int = 256) -> None:
        self._data: Dict[str, Any] = {}
        self._maxsize = maxsize
        self._lock = threading.Lock()

    def get(self, key: str) -> Any:
        with self._lock:
            return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if key in self._data:
                del self._data[key]
            elif len(self._data) >= self._maxsize:
                oldest = next(iter(self._data))
                del self._data[oldest]
            self._data[key] = value

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __contains__(self, key: str) -> bool:
        with self._lock:
            return key in self._data

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


# ---------------------------------------------------------------------------
# DownloadManager
# ---------------------------------------------------------------------------


class DownloadManager:
    """Priority queue + ThreadPoolExecutor for segment downloads."""

    def __init__(self, num_workers: Optional[int] = None) -> None:
        self._workers = num_workers or settings.DOWNLOAD_WORKERS
        self._queue: PriorityQueue[SegmentTask] = PriorityQueue()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._seq = 0
        self._seq_lock = threading.Lock()
        self._downloading: Dict[str, Set[int]] = {}  # song_id -> set of indices in flight
        self._dl_lock = threading.Lock()
        self._shutdown = False
        self._task_handler: Optional[Callable[[SegmentTask], None]] = None

    def set_handler(self, handler: Callable[[SegmentTask], None]) -> None:
        self._task_handler = handler

    def start(self) -> None:
        if self._executor is not None:
            return
        self._shutdown = False
        self._executor = ThreadPoolExecutor(
            max_workers=self._workers,
            thread_name_prefix="dl-worker",
        )
        for _ in range(self._workers):
            self._executor.submit(self._worker_loop)
        logger.info("DownloadManager started with %d workers", self._workers)

    def stop(self) -> None:
        self._shutdown = True
        # Wake workers
        for _ in range(self._workers):
            try:
                self._queue.put_nowait(SegmentTask("", -1, Priority.LOW, 0, seq=-1))
            except Exception:
                pass
        if self._executor is not None:
            self._executor.shutdown(wait=True, cancel_futures=True)
            self._executor = None
        logger.info("DownloadManager stopped")

    def _worker_loop(self) -> None:
        while not self._shutdown:
            try:
                task = self._queue.get(timeout=1.0)
            except Empty:
                continue
            if self._shutdown:
                break
            if task.seq == -1:  # sentinel
                continue
            try:
                if self._task_handler:
                    self._task_handler(task)
            except Exception as e:
                logger.error("Worker error on %s seg %d: %s", task.song_id, task.index, e)
            finally:
                self._queue.task_done()
                with self._dl_lock:
                    indices = self._downloading.get(task.song_id)
                    if indices:
                        indices.discard(task.index)
                        if not indices:
                            del self._downloading[task.song_id]

    def enqueue(self, song_id: str, index: int, priority: Priority, epoch: int) -> bool:
        """Enqueue a segment download. Returns False if already downloading."""
        with self._dl_lock:
            indices = self._downloading.setdefault(song_id, set())
            if index in indices:
                return False
            indices.add(index)

        with self._seq_lock:
            self._seq += 1
            seq = self._seq

        self._queue.put(SegmentTask(song_id, index, priority, epoch, seq))
        return True

    def is_downloading(self, song_id: str, index: int) -> bool:
        with self._dl_lock:
            return index in self._downloading.get(song_id, set())

    def queue_size(self) -> int:
        return self._queue.qsize()


# ---------------------------------------------------------------------------
# StreamingService
# ---------------------------------------------------------------------------


class StreamingService:
    """Thread-safe singleton: DASH segment streaming, cache, playback session."""

    STREAM_URL_TTL_S = 6 * 3600  # ~6 hours (P4)
    EXTRACT_FAILURE_TTL_S = 300  # 5 min negative cache for failed extractions

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._auth = get_auth_service()
        self._dl_manager = DownloadManager()
        self._dl_manager.set_handler(self._process_task)

        # Bounded in-memory caches (P19)
        self._stream_info_cache: BoundedDict = BoundedDict(256)
        self._stream_url_cache: BoundedDict = BoundedDict(256)      # song_id -> (url, fetched_at)
        self._segment_table_cache: BoundedDict = BoundedDict(256)   # song_id -> StreamInfo
        self._extract_failures: Dict[str, float] = {}               # song_id -> failed_at (negative cache)
        self._epochs: Dict[str, int] = {}                            # song_id -> epoch
        self._epochs_lock = threading.Lock()

        # Per-song segment status (in-memory mirror of DB)
        self._seg_status: Dict[str, Dict[int, SegmentStatus]] = {}
        self._seg_status_lock = threading.Lock()

        # Playback session
        self._playback = PlaybackInfo()
        self._playback_lock = threading.Lock()

        # HTTP session for CDN requests
        self._http = requests.Session()

    # --- Lifecycle ---

    def start(self) -> None:
        self._dl_manager.start()
        self.reconcile_cache()

    def stop(self) -> None:
        self._dl_manager.stop()

    # --- Epoch management (P18) ---

    def get_epoch(self, song_id: str) -> int:
        with self._epochs_lock:
            return self._epochs.get(song_id, 0)

    def bump_epoch(self, song_id: str) -> int:
        with self._epochs_lock:
            new_epoch = self._epochs.get(song_id, 0) + 1
            self._epochs[song_id] = new_epoch
            with self._playback_lock:
                if self._playback.song_id == song_id:
                    self._playback.epoch = new_epoch
            logger.info("Epoch bumped for %s -> %d", song_id, new_epoch)
            return new_epoch

    # --- Playback session ---

    def start_playback(self, song_id: str) -> Dict[str, Any]:
        validate_song_id(song_id)
        epoch = self.get_epoch(song_id)
        with self._playback_lock:
            self._playback = PlaybackInfo(
                song_id=song_id,
                position_ms=0,
                is_playing=True,
                epoch=epoch,
                last_updated=time.time(),
            )
        # Queue init + segment 0 at CRITICAL, next 2 HIGH, rest NORMAL
        self._queue_buffer_ahead(song_id, start_index=0)
        return {"message": "playback started", "song_id": song_id, "epoch": epoch}

    def pause_playback(self) -> Dict[str, Any]:
        with self._playback_lock:
            self._playback.is_playing = False
            self._playback.last_updated = time.time()
        return {"message": "paused"}

    def resume_playback(self) -> Dict[str, Any]:
        with self._playback_lock:
            self._playback.is_playing = True
            self._playback.last_updated = time.time()
            song_id = self._playback.song_id
            pos = self._playback.position_ms
        if song_id:
            self._queue_buffer_ahead(song_id, start_index=self._position_to_index(song_id, pos))
        return {"message": "resumed"}

    def stop_playback(self) -> Dict[str, Any]:
        with self._playback_lock:
            song_id = self._playback.song_id
            self._playback = PlaybackInfo()
        if song_id:
            self.bump_epoch(song_id)
        return {"message": "stopped"}

    def update_position(self, position_ms: int) -> Dict[str, Any]:
        with self._playback_lock:
            self._playback.position_ms = position_ms
            self._playback.last_updated = time.time()
            song_id = self._playback.song_id
            self._playback.current_segment_index = (
                self._position_to_index(song_id, position_ms) if song_id else 0
            )
        if song_id:
            self._queue_buffer_ahead(song_id, start_index=self._playback.current_segment_index)
        return {"message": "position updated", "position_ms": position_ms}

    def seek(self, position_ms: int) -> Dict[str, Any]:
        with self._playback_lock:
            song_id = self._playback.song_id
        if not song_id:
            return {"message": "no active song"}
        epoch = self.bump_epoch(song_id)
        with self._playback_lock:
            self._playback.position_ms = position_ms
            self._playback.last_updated = time.time()
        start_index = self._position_to_index(song_id, position_ms)
        with self._playback_lock:
            self._playback.current_segment_index = start_index
        self._queue_buffer_ahead(song_id, start_index=start_index, epoch=epoch)
        return {"message": "seeked", "position_ms": position_ms, "segment_index": start_index, "epoch": epoch}

    def get_playback_state(self) -> Dict[str, Any]:
        with self._playback_lock:
            return self._playback.to_dict()

    def buffer_ahead(self, song_id: str) -> Dict[str, Any]:
        validate_song_id(song_id)
        with self._playback_lock:
            start = self._playback.current_segment_index if self._playback.song_id == song_id else 0
        self._queue_buffer_ahead(song_id, start_index=start)
        return {"message": "buffer-ahead triggered", "song_id": song_id}

    def _position_to_index(self, song_id: str, position_ms: int) -> int:
        info = self._get_stream_info(song_id)
        if info and info.segments:
            return position_ms_to_segment_index(info, position_ms)
        return 0

    def _queue_buffer_ahead(self, song_id: str, start_index: int = 0, epoch: Optional[int] = None) -> None:
        """Queue init + segments around the playhead with priority levels."""
        if epoch is None:
            epoch = self.get_epoch(song_id)

        info = self._get_stream_info(song_id)
        if not info:
            logger.warning("Cannot buffer-ahead: no stream info for %s", song_id)
            return

        # Init at CRITICAL (skip if no init segment — e.g. progressive streams)
        if info.has_init:
            self._dl_manager.enqueue(song_id, -1, Priority.CRITICAL, epoch)

        # Segment at start_index at CRITICAL, next 2 HIGH, then NORMAL until the
        # window (measured from the playhead, not the song start) is covered
        ahead_ms = 0
        for idx in range(start_index, len(info.segments)):
            offset = idx - start_index
            if offset == 0:
                pri = Priority.CRITICAL
            elif offset <= 2:
                pri = Priority.HIGH
            elif ahead_ms > settings.SEGMENT_BUFFER_AHEAD_SEC * 1000:
                break  # beyond buffer window
            else:
                pri = Priority.NORMAL
            self._dl_manager.enqueue(song_id, idx, pri, epoch)
            ahead_ms += info.segments[idx].duration_ms

    # --- Stream info (manifest fetch + parse) ---

    def get_stream_info(self, song_id: str) -> Optional[StreamInfo]:
        validate_song_id(song_id)
        return self._get_stream_info(song_id)

    def _get_stream_info(self, song_id: str) -> Optional[StreamInfo]:
        cached = self._stream_info_cache.get(song_id)
        if cached is not None:
            return cached

        try:
            info = self._build_stream_info(song_id)
            if info:
                self._stream_info_cache.set(song_id, info)
                self._segment_table_cache.set(song_id, info)
            return info
        except Exception as e:
            logger.error("Failed to build stream info for %s: %s", song_id, e)
            return None

    def _build_stream_info(self, song_id: str) -> Optional[StreamInfo]:
        """Fetch stream URL via yt-dlp, then fetch manifest and parse."""
        url = self._get_stream_url(song_id)
        if not url:
            logger.error("No stream URL for %s", song_id)
            return None

        headers = self._auth.get_cdn_headers()

        # Fetch the URL to check if it's DASH (XML) or progressive (binary)
        try:
            resp = self._http.get(
                url,
                headers={**headers, "Range": "bytes=0-1023"},
                timeout=(settings.HTTP_TIMEOUT_CONNECT_S, settings.HTTP_TIMEOUT_READ_S),
                stream=True,
            )
        except requests.RequestException as e:
            logger.error("Failed to fetch stream URL for %s: %s", song_id, e)
            return None

        content_type = resp.headers.get("Content-Type", "")
        first_bytes = resp.content[:1024]
        resp.close()

        # Check if DASH manifest
        is_xml = (
            first_bytes.lstrip().startswith(b"<?xml")
            or first_bytes.lstrip().startswith(b"<MPD")
            or "dash" in content_type.lower()
            or "mpd" in content_type.lower()
        )

        if is_xml:
            try:
                manifest_resp = self._http.get(
                    url,
                    headers=headers,
                    timeout=(settings.HTTP_TIMEOUT_CONNECT_S, settings.HTTP_TIMEOUT_READ_S),
                )
                manifest_resp.raise_for_status()
                title = self._get_song_title(song_id)
                info = parse_mpd(
                    manifest_resp.content,
                    song_id=song_id,
                    title=title,
                    mime_hint="audio/mp4",
                )
                info.base_url = url if not info.base_url else info.base_url
                logger.info(
                    "DASH manifest parsed for %s: %d segments, %d bytes, mime=%s",
                    song_id, len(info.segments), info.total_bytes, info.mime_type,
                )
                return info
            except Exception as e:
                logger.error("Failed to parse DASH manifest for %s: %s", song_id, e)
                return None
        else:
            return self._build_progressive_info(song_id, url, headers)

    def _build_progressive_info(self, song_id: str, url: str, headers: Dict[str, str]) -> Optional[StreamInfo]:
        """Progressive fallback: determine file size, create proportional segments."""
        total_bytes = self._probe_content_length(url, headers)
        if total_bytes <= 0:
            logger.error("Cannot determine size for progressive stream %s", song_id)
            return None

        duration_ms = self._get_song_duration(song_id)
        if duration_ms <= 0:
            duration_ms = 180_000  # fallback 3 min

        bytes_per_ms = total_bytes / duration_ms
        seg_duration_ms = settings.SEGMENT_TARGET_SEC * 1000
        seg_size = int(bytes_per_ms * seg_duration_ms)

        segments: List[DashSegmentInfo] = []
        offset = 0
        idx = 0
        while offset < total_bytes:
            end = min(offset + seg_size - 1, total_bytes - 1)
            segments.append(DashSegmentInfo(
                index=idx,
                byte_start=offset,
                byte_end=end,
                duration_ms=int((end - offset + 1) / bytes_per_ms) if bytes_per_ms > 0 else seg_duration_ms,
                url=url,
            ))
            offset = end + 1
            idx += 1

        info = StreamInfo(
            song_id=song_id,
            title=self._get_song_title(song_id),
            duration_ms=duration_ms,
            mime_type="audio/mp4",
            init_range=(0, -1),  # no init segment — first segment starts at byte 0
            segments=segments,
            is_dash=False,
            base_url=url,
        )
        logger.info(
            "Progressive fallback for %s: %d segments, %d bytes",
            song_id, len(segments), total_bytes,
        )
        return info

    def _probe_content_length(self, url: str, headers: Dict[str, str]) -> int:
        """P5: Three strategies to get content length. Returns 0 on failure."""
        # Strategy 1: clen= param
        try:
            clen_url = url + ("&" if "?" in url else "?") + "clen=1"
            resp = self._http.head(
                clen_url, headers=headers, allow_redirects=True,
                timeout=(settings.HTTP_TIMEOUT_CONNECT_S, settings.HTTP_TIMEOUT_READ_S),
            )
            cl = resp.headers.get("Content-Length")
            if cl and int(cl) > 0:
                return int(cl)
        except Exception:
            pass

        # Strategy 2: HEAD on original URL
        try:
            resp = self._http.head(
                url, headers=headers, allow_redirects=True,
                timeout=(settings.HTTP_TIMEOUT_CONNECT_S, settings.HTTP_TIMEOUT_READ_S),
            )
            cl = resp.headers.get("Content-Length")
            if cl and int(cl) > 0:
                return int(cl)
        except Exception:
            pass

        # Strategy 3: Range probe bytes=0-0
        try:
            resp = self._http.get(
                url, headers={**headers, "Range": "bytes=0-0"},
                timeout=(settings.HTTP_TIMEOUT_CONNECT_S, settings.HTTP_TIMEOUT_READ_S),
            )
            cr = resp.headers.get("Content-Range", "")
            resp.close()
            m = re.search(r"/(\d+)", cr)
            if m:
                return int(m.group(1))
        except Exception:
            pass

        return 0

    def _get_stream_url(self, song_id: str) -> Optional[str]:
        """Get the stream URL via yt-dlp. Cached per song with TTL (P3, P4).

        Also has a negative cache: if extraction recently failed, return None
        immediately without retrying yt-dlp (avoids hammering on broken videos).
        """
        cached = self._stream_url_cache.get(song_id)
        if cached is not None:
            url, fetched_at = cached
            if time.time() - fetched_at < self.STREAM_URL_TTL_S:
                return url
            logger.info("Stream URL expired for %s, refreshing", song_id)

        # Negative cache: skip if recently failed
        failed_at = self._extract_failures.get(song_id)
        if failed_at is not None:
            if time.time() - failed_at < self.EXTRACT_FAILURE_TTL_S:
                logger.debug("Skipping extraction for %s (recently failed)", song_id)
                return None
            else:
                del self._extract_failures[song_id]

        return self._extract_stream_url(song_id)

    def _extract_stream_url(self, song_id: str) -> Optional[str]:
        """Use yt-dlp to extract the stream URL. P2: js_runtimes=node required.

        Multi-strategy approach to avoid "The page needs to be reloaded" error:
        - Tries multiple player clients (android, web_safari, tv_embedded, mweb)
        - Uses www.youtube.com (music.youtube.com subdomain triggers reload more often)
        - Format selector: 'bestaudio/best' then falls back to 'best'

        Until Phase 0 the options used list-form extractor_args, which yt-dlp
        ignores, so every attempt ran with yt-dlp's default client. With the
        shape fixed (build_ydl_opts) the rotation below takes effect.
        """
        cookie_file = None
        try:
            if self._auth.is_authenticated:
                cookie_file = self._auth.write_netscape_cookie_file()

            watch_url = f"https://www.youtube.com/watch?v={song_id}"

            # Strategy list: (player_client, format_selector); None = yt-dlp's
            # default client. Default goes first: without a PO token, android
            # only returns muxed itag 18 (360p video), never audio-only itag 140.
            # "worst" is the last resort per client. Phase 1 makes this a setting.
            strategies: List[Tuple[Optional[str], str]] = [
                (None, "bestaudio/best"),
                (None, "best"),
                (None, "worst"),
                ("android", "bestaudio/best"),
                ("android", "best"),
                ("android", "worst"),
                ("web_safari", "bestaudio/best"),
                ("web_safari", "best"),
                ("web_safari", "worst"),
                ("tv_embedded", "bestaudio/best"),
                ("tv_embedded", "best"),
                ("tv_embedded", "worst"),
                ("mweb", "bestaudio/best"),
                ("mweb", "best"),
                ("mweb", "worst"),
            ]

            for player_client, fmt in strategies:
                client_label = player_client or "default"
                logger.info(
                    "Trying extraction for %s: player_client=%s, format=%s",
                    song_id, client_label, fmt,
                )

                ydl_opts = build_ydl_opts(player_client, fmt, cookie_file)
                prefer_audio = (fmt in ("best", "worst"))
                url = self._try_extract(ydl_opts, watch_url, song_id, prefer_audio=prefer_audio)

                if url:
                    self._stream_url_cache.set(song_id, (url, time.time()))
                    self._extract_failures.pop(song_id, None)
                    logger.info(
                        "Extracted stream URL for %s via player_client=%s, format=%s",
                        song_id, client_label, fmt,
                    )
                    return url

                logger.warning(
                    "Extraction failed for %s with player_client=%s, format=%s — trying next strategy",
                    song_id, client_label, fmt,
                )

            logger.error("No stream URL found for %s after all %d strategies", song_id, len(strategies))
            self._log_available_formats(song_id, cookie_file)
            self._extract_failures[song_id] = time.time()
            return None

        except Exception as e:
            logger.error("yt-dlp extraction failed for %s: %s", song_id, e)
            self._extract_failures[song_id] = time.time()
            return None
        finally:
            if cookie_file:
                try:
                    os.unlink(cookie_file)  # P23: always delete
                except OSError:
                    pass

    def _log_available_formats(self, song_id: str, cookie_file: Optional[str]) -> None:
        """Diagnostic: extract with no format selector and log available format IDs.

        Called when all extraction strategies fail, to help debug why a video
        has no playable formats (region-lock, age-restriction, etc.).
        """
        try:
            from yt_dlp import YoutubeDL

            watch_url = f"https://www.youtube.com/watch?v={song_id}"
            ydl_opts = build_ydl_opts(None, None, cookie_file)
            ydl_opts["listformats"] = True

            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(watch_url, download=False)

            formats = info.get("formats", [])
            if not formats:
                logger.error("Diagnostic for %s: no formats returned at all (video may be private, deleted, or region-locked)", song_id)
                return

            fmt_list = []
            for f in formats:
                fid = f.get("format_id", "?")
                ext = f.get("ext", "?")
                acodec = f.get("acodec", "?")
                vcodec = f.get("vcodec", "?")
                abr = f.get("abr", f.get("tbr", 0))
                url_present = "yes" if f.get("url") else "NO"
                fmt_list.append(f"  itag={fid} ext={ext} acodec={acodec} vcodec={vcodec} abr={abr} url={url_present}")

            audio_count = sum(1 for f in formats if f.get("acodec") and f["acodec"] != "none")
            logger.error(
                "Diagnostic for %s: %d total formats, %d with audio:\n%s",
                song_id, len(formats), audio_count, "\n".join(fmt_list),
            )
        except Exception as e:
            logger.error("Diagnostic extraction failed for %s: %s", song_id, e)

    def _try_extract(
        self,
        ydl_opts: Dict[str, Any],
        watch_url: str,
        song_id: str,
        prefer_audio: bool = False,
    ) -> Optional[str]:
        """Single yt-dlp extraction attempt. Returns the stream URL or None.

        Catches DownloadError internally so the caller's fallback logic can
        run. Prefers itag 140 (AAC/MP4) from the formats list over yt-dlp's
        auto-selected format (which may be Opus/WebM itag 251).

        If yt-dlp raises "Requested format is not available", retries without
        a format selector so yt-dlp uses its default and we can filter in Python.
        """
        from yt_dlp import YoutubeDL
        from yt_dlp.utils import DownloadError

        info = None

        # First attempt: with the specified format selector
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(watch_url, download=False)
        except DownloadError as e:
            err_str = str(e)
            if "not available" in err_str.lower() or "format is not available" in err_str.lower():
                # Format selector matched nothing — retry without format key
                # so yt-dlp uses its default and returns all formats for Python-side filtering
                logger.info(
                    "Format selector '%s' matched nothing for %s, retrying without format selector",
                    ydl_opts.get("format", "(default)"), song_id,
                )
                retry_opts = {k: v for k, v in ydl_opts.items() if k != "format"}
                try:
                    with YoutubeDL(retry_opts) as ydl:
                        info = ydl.extract_info(watch_url, download=False)
                except DownloadError as e2:
                    logger.warning("yt-dlp retry without format also failed for %s: %s", song_id, e2)
                    return None
                except Exception as e2:
                    logger.error("yt-dlp retry without format error for %s: %s", song_id, e2)
                    return None
            else:
                logger.warning("yt-dlp format selection failed for %s: %s", song_id, e)
                return None
        except Exception as e:
            logger.error("yt-dlp extraction error for %s: %s", song_id, e)
            return None

        if info is None:
            return None

        fmt = self._select_audio_format(info, song_id, prefer_audio)
        if fmt is None:
            return None
        _wait_until_available(fmt, song_id)
        return fmt["url"]

    def _select_audio_format(
        self, info: Dict[str, Any], song_id: str, prefer_audio: bool
    ) -> Optional[Dict[str, Any]]:
        """Pick the format dict (with a "url") to stream from a yt-dlp info dict."""
        # First, scan formats list for our preferred itag (140 = AAC/MP4)
        if "formats" in info:
            for f in info["formats"]:
                if (
                    str(f.get("format_id", "")) == settings.STREAM_FORMAT
                    and f.get("acodec")
                    and f["acodec"] != "none"
                    and f.get("url")
                ):
                    return f

        # Use yt-dlp's selected format URL
        if "url" in info:
            if prefer_audio:
                acodec = info.get("acodec", "")
                vcodec = info.get("vcodec", "none")
                if vcodec != "none" and acodec != "none":
                    # Has both video and audio — try to find audio-only in formats
                    pass  # fall through to formats filtering
                elif acodec and acodec != "none":
                    return info
            else:
                return info

        # Filter from formats list for audio-only
        if "formats" in info:
            audio_formats = [
                f for f in info["formats"]
                if f.get("acodec") and f["acodec"] != "none" and f.get("url")
            ]
            if not audio_formats:
                # No audio-only formats — log available formats for debugging
                avail = [f.get("format_id", "?") for f in info.get("formats", [])[:10]]
                logger.error("No audio formats for %s. Available: %s", song_id, avail)
                return None

            # Prefer MP4 container (m4a) for webview compatibility
            mp4_audio = [f for f in audio_formats if f.get("ext") in ("mp4", "m4a")]
            if mp4_audio:
                mp4_audio.sort(key=lambda f: f.get("abr") or f.get("tbr") or 0, reverse=True)
                return mp4_audio[0]

            # Fall back to highest bitrate audio
            audio_formats.sort(key=lambda f: f.get("abr") or f.get("tbr") or 0, reverse=True)
            return audio_formats[0]

        # requested_formats (DASH/HLS split)
        if "requested_formats" in info:
            for f in info["requested_formats"]:
                if f.get("acodec") and f["acodec"] != "none" and f.get("url"):
                    return f

        return None

    def refresh_stream_url(self, song_id: str) -> Optional[str]:
        """Force refresh the stream URL (P4: on 403)."""
        self._stream_url_cache.delete(song_id)
        self._stream_info_cache.delete(song_id)
        self._segment_table_cache.delete(song_id)
        self._extract_failures.pop(song_id, None)
        return self._extract_stream_url(song_id)

    # --- Segment status ---

    def get_segment_status(self, song_id: str, index: int) -> SegmentStatus:
        with self._seg_status_lock:
            return self._seg_status.get(song_id, {}).get(index, SegmentStatus.PENDING)

    def set_segment_status(self, song_id: str, index: int, status: SegmentStatus) -> None:
        with self._seg_status_lock:
            self._seg_status.setdefault(song_id, {})[index] = status

    def get_all_segment_statuses(self, song_id: str) -> List[Dict[str, Any]]:
        """Return segment status list for visualization (SegmentBar)."""
        info = self._get_stream_info(song_id)
        if not info:
            return []
        result = []
        # Init (skip if no init segment — e.g. progressive streams)
        if info.has_init:
            init_status = self.get_segment_status(song_id, -1)
            init_path = self._segment_path(song_id, -1)
            if init_path.exists():
                init_status = SegmentStatus.DOWNLOADED
            result.append({
                "index": -1,
                "status": init_status.value,
                "duration_ms": 0,
                "size_bytes": info.init_size,
            })
        for seg in info.segments:
            status = self.get_segment_status(song_id, seg.index)
            path = self._segment_path(song_id, seg.index)
            if path.exists():
                status = SegmentStatus.DOWNLOADED
            result.append({
                "index": seg.index,
                "status": status.value,
                "duration_ms": seg.duration_ms,
                "size_bytes": seg.byte_end - seg.byte_start + 1,
            })
        return result

    # --- Segment download (the robustness-critical path, §6.5) ---

    def _process_task(self, task: SegmentTask) -> None:
        """Worker callback: download a single segment."""
        song_id = task.song_id
        index = task.index

        # Check epoch: if stale, skip (P18)
        current_epoch = self.get_epoch(song_id)
        if task.epoch < current_epoch:
            logger.debug("Skipping stale task %s seg %d (epoch %d < %d)", song_id, index, task.epoch, current_epoch)
            return

        # Check if already downloaded
        path = self._segment_path(song_id, index)
        if path.exists():
            self.set_segment_status(song_id, index, SegmentStatus.DOWNLOADED)
            return

        self.set_segment_status(song_id, index, SegmentStatus.DOWNLOADING)
        self._download_segment_with_retry(song_id, index, task.epoch)

    def _download_segment_with_retry(self, song_id: str, index: int, epoch: int) -> None:
        """Download with retry logic (§6.5 step 6)."""
        info = self._get_stream_info(song_id)
        if not info:
            self.set_segment_status(song_id, index, SegmentStatus.ERROR)
            return

        if index == -1:
            if not info.has_init:
                # No init segment (e.g. progressive stream) — nothing to download
                self.set_segment_status(song_id, index, SegmentStatus.DOWNLOADED)
                return
            byte_start, byte_end = info.init_range
            duration_ms = 0
        else:
            if index >= len(info.segments):
                self.set_segment_status(song_id, index, SegmentStatus.ERROR)
                return
            seg = info.segments[index]
            byte_start, byte_end = seg.byte_start, seg.byte_end
            duration_ms = seg.duration_ms

        expected_size = byte_end - byte_start + 1
        url = info.base_url

        for attempt in range(settings.MAX_RETRIES):
            if epoch < self.get_epoch(song_id):
                logger.debug("Aborting stale download %s seg %d", song_id, index)
                return

            try:
                success = self._download_segment_attempt(
                    song_id, index, url, byte_start, byte_end, expected_size, duration_ms
                )
                if success:
                    self.set_segment_status(song_id, index, SegmentStatus.DOWNLOADED)
                    self._record_segment_db(song_id, index, byte_start, byte_end, expected_size, duration_ms)
                    self._touch_segment(song_id, index)
                    self.cleanup_cache()
                    return
            except _Auth403Error:
                # P4: refresh stream URL and rebuild. A CDN 403 means the signed
                # URL expired — not the YouTube session, so auth state is untouched
                # and the refresh still extracts with cookies.
                logger.warning("403 on %s seg %d, refreshing stream URL", song_id, index)
                new_info = self._rebuild_after_403(song_id)
                if new_info is None:
                    self.set_segment_status(song_id, index, SegmentStatus.ERROR)
                    return
                info = new_info
                if index == -1:
                    if not info.has_init:
                        self.set_segment_status(song_id, index, SegmentStatus.DOWNLOADED)
                        return
                    byte_start, byte_end = info.init_range
                else:
                    if index < len(info.segments):
                        seg = info.segments[index]
                        byte_start, byte_end = seg.byte_start, seg.byte_end
                    else:
                        self.set_segment_status(song_id, index, SegmentStatus.ERROR)
                        return
                expected_size = byte_end - byte_start + 1
                url = info.base_url
                try:
                    success = self._download_segment_attempt(
                        song_id, index, url, byte_start, byte_end, expected_size, duration_ms
                    )
                    if success:
                        self.set_segment_status(song_id, index, SegmentStatus.DOWNLOADED)
                        self._record_segment_db(song_id, index, byte_start, byte_end, expected_size, duration_ms)
                        self._touch_segment(song_id, index)
                        self.cleanup_cache()
                        return
                except Exception as e:
                    logger.error("Retry after 403 refresh failed for %s seg %d: %s", song_id, index, e)
                self.set_segment_status(song_id, index, SegmentStatus.ERROR)
                return
            except _PermanentError as e:
                logger.error("Permanent error downloading %s seg %d: %s", song_id, index, e)
                self.set_segment_status(song_id, index, SegmentStatus.ERROR)
                return
            except Exception as e:
                logger.warning("Attempt %d/%d failed for %s seg %d: %s", attempt + 1, settings.MAX_RETRIES, song_id, index, e)

            if attempt < settings.MAX_RETRIES - 1:
                backoff = [0.5, 1.0, 2.0][min(attempt, 2)]
                jitter = random.uniform(0, 0.3)
                time.sleep(backoff + jitter)

        self.set_segment_status(song_id, index, SegmentStatus.ERROR)
        logger.error("All %d attempts failed for %s seg %d", settings.MAX_RETRIES, song_id, index)

    def _download_segment_attempt(
        self,
        song_id: str,
        index: int,
        url: str,
        byte_start: int,
        byte_end: int,
        expected_size: int,
        duration_ms: int,
    ) -> bool:
        """Single download attempt. P14: verify 206 + Content-Range + byte count."""
        if not url:
            raise _PermanentError("No URL for segment")

        headers = self._auth.get_cdn_headers()
        headers["Range"] = f"bytes={byte_start}-{byte_end}"

        resp = self._http.get(
            url,
            headers=headers,
            timeout=(settings.HTTP_TIMEOUT_CONNECT_S, settings.HTTP_TIMEOUT_READ_S),
            stream=True,
        )

        try:
            # P14: Verify 206
            if resp.status_code == 403:
                raise _Auth403Error("403 Forbidden")
            if resp.status_code == 429:
                raise _TransientError("429 Too Many Requests")
            if resp.status_code >= 500:
                raise _TransientError(f"Server error {resp.status_code}")
            if resp.status_code == 200:
                # Range ignored — P14: never save
                raise _PermanentError("Server returned 200 (range ignored)")
            if resp.status_code != 206:
                if 400 <= resp.status_code < 500:
                    raise _PermanentError(f"Client error {resp.status_code}")
                raise _TransientError(f"Unexpected status {resp.status_code}")

            # P14: Verify Content-Range matches
            content_range = resp.headers.get("Content-Range", "")
            expected_cr = f"bytes {byte_start}-{byte_end}/"
            if not content_range.startswith(expected_cr):
                raise _PermanentError(f"Content-Range mismatch: {content_range!r} != {expected_cr!r}")

            # Read and verify byte count
            chunks = []
            received = 0
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    chunks.append(chunk)
                    received += len(chunk)

            # P14: Verify byte count
            if received != expected_size:
                raise _TransientError(f"Short read: {received} != {expected_size}")

            data = b"".join(chunks)

            # P15: Atomic write
            self._atomic_write_segment(song_id, index, data)
            return True

        finally:
            resp.close()

    def _atomic_write_segment(self, song_id: str, index: int, data: bytes) -> None:
        """P15: tmp file + os.replace()."""
        final_path = self._segment_path(song_id, index)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = final_path.with_suffix(".tmp")
        with open(tmp_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp_path), str(final_path))

    def _segment_path(self, song_id: str, index: int) -> Path:
        if index == -1:
            return settings.segments_dir / song_id / "init.bin"
        return settings.segments_dir / song_id / f"{index:04d}.bin"

    def download_segment_sync(self, song_id: str, index: int) -> bool:
        """Synchronously download a segment (used by the audio endpoint for G1)."""
        # No init segment — nothing to download
        if index == -1:
            info = self._get_stream_info(song_id)
            if info and not info.has_init:
                return True
        path = self._segment_path(song_id, index)
        if path.exists():
            return True

        if self._dl_manager.is_downloading(song_id, index):
            deadline = time.time() + 30
            while time.time() < deadline:
                if path.exists():
                    return True
                time.sleep(0.05)
            return path.exists()

        epoch = self.get_epoch(song_id)
        self.set_segment_status(song_id, index, SegmentStatus.DOWNLOADING)
        self._download_segment_with_retry(song_id, index, epoch)
        return path.exists()

    # --- DB recording ---

    def _record_segment_db(
        self, song_id: str, index: int, byte_start: int, byte_end: int,
        size_bytes: int, duration_ms: int,
    ) -> None:
        try:
            with session_scope() as session:
                existing = session.get(Segment, (song_id, index))
                if existing:
                    existing.status = SegmentStatus.DOWNLOADED.value
                    existing.size_bytes = size_bytes
                    existing.last_accessed = dt.datetime.utcnow()
                else:
                    session.add(Segment(
                        song_id=song_id,
                        index=index,
                        byte_start=byte_start,
                        byte_end=byte_end,
                        size_bytes=size_bytes,
                        duration_ms=duration_ms,
                        status=SegmentStatus.DOWNLOADED.value,
                        file_path=str(self._segment_path(song_id, index)),
                    ))
        except Exception as e:
            logger.error("Failed to record segment DB row %s seg %d: %s", song_id, index, e)

    def _touch_segment(self, song_id: str, index: int) -> None:
        try:
            with session_scope() as session:
                seg = session.get(Segment, (song_id, index))
                if seg:
                    seg.last_accessed = dt.datetime.utcnow()
        except Exception:
            pass

    def _rebuild_after_403(self, song_id: str) -> Optional[StreamInfo]:
        """Refresh stream URL and rebuild segment table (P4)."""
        self.refresh_stream_url(song_id)
        info =self._build_stream_info(song_id)
        if info:
            self._stream_info_cache.set(song_id, info)
            self._segment_table_cache.set(song_id, info)
        return info

    # --- Cache management (§6.6) ---

    def cleanup_cache(self) -> None:
        """LRU eviction: if over CACHE_MAX_SIZE_MB, evict down to 80%."""
        try:
            segments_dir = settings.segments_dir
            if not segments_dir.exists():
                return

            total = 0
            files: List[Tuple[Path, int, float]] = []
            for song_dir in segments_dir.iterdir():
                if not song_dir.is_dir():
                    continue
                for f in song_dir.iterdir():
                    if f.is_file() and not f.name.endswith(".tmp"):
                        try:
                            stat = f.stat()
                            total += stat.st_size
                            files.append((f, stat.st_size, stat.st_mtime))
                        except OSError:
                            pass

            max_bytes = settings.cache_max_bytes
            if total <= max_bytes:
                return

            target = int(max_bytes * 0.80)
            logger.info("Cache over limit (%d > %d), evicting to %d", total, max_bytes, target)

            # Protect currently playing song's segments ahead of playhead
            protected: Set[Path] = set()
            with self._playback_lock:
                playing_song = self._playback.song_id
                current_idx = self._playback.current_segment_index
            if playing_song:
                playing_dir = segments_dir / playing_song
                if playing_dir.exists():
                    for f in playing_dir.iterdir():
                        if f.name == "init.bin":
                            protected.add(f)
                        elif f.suffix == ".bin":
                            try:
                                idx = int(f.stem)
                                if idx >= current_idx - settings.SEGMENT_BEHIND:
                                    protected.add(f)
                            except ValueError:
                                pass

            files.sort(key=lambda x: x[2])  # LRU by mtime

            for path, size, _ in files:
                if total <= target:
                    break
                if path in protected:
                    continue
                try:
                    path.unlink(missing_ok=True)
                    total -= size
                    self._delete_segment_db_row(path)
                    logger.debug("Evicted %s (%d bytes)", path, size)
                except OSError:
                    pass

            for song_dir in segments_dir.iterdir():
                if song_dir.is_dir():
                    try:
                        song_dir.rmdir()
                    except OSError:
                        pass

            logger.info("Cache cleanup done: %d bytes remaining", total)

        except Exception as e:
            logger.error("Cache cleanup failed: %s", e)

    def _delete_segment_db_row(self, path: Path) -> None:
        try:
            song_id = path.parent.name
            if path.name == "init.bin":
                index = -1
            else:
                index = int(path.stem)
            with session_scope() as session:
                seg = session.get(Segment, (song_id, index))
                if seg:
                    session.delete(seg)
        except Exception:
            pass

    def get_cache_info(self) -> Dict[str, Any]:
        """Return cache statistics: total size, file count, per-song breakdown."""
        segments_dir = settings.segments_dir
        total_bytes = 0
        file_count = 0
        song_count = 0
        songs: List[Dict[str, Any]] = []

        if segments_dir.exists():
            for song_dir in sorted(segments_dir.iterdir()):
                if not song_dir.is_dir():
                    continue
                song_count += 1
                song_bytes = 0
                song_files = 0
                for f in song_dir.iterdir():
                    if f.is_file() and not f.name.endswith(".tmp"):
                        try:
                            size = f.stat().st_size
                            total_bytes += size
                            song_bytes += size
                            file_count += 1
                            song_files += 1
                        except OSError:
                            pass
                songs.append({
                    "song_id": song_dir.name,
                    "size_bytes": song_bytes,
                    "file_count": song_files,
                })

        max_bytes = settings.cache_max_bytes
        return {
            "total_bytes": total_bytes,
            "total_mb": round(total_bytes / (1024 * 1024), 2),
            "max_mb": settings.CACHE_MAX_SIZE_MB,
            "usage_pct": round(total_bytes / max_bytes * 100, 1) if max_bytes > 0 else 0,
            "file_count": file_count,
            "song_count": song_count,
            "songs": songs,
        }

    def reconcile_cache(self) -> None:
        """Startup reconciliation: heal crash damage (§6.6)."""
        logger.info("Reconciling segment cache...")
        segments_dir = settings.segments_dir
        if not segments_dir.exists():
            return

        orphans_deleted = 0
        missing_deleted = 0
        mismatches_deleted = 0

        db_rows: Dict[Tuple[str, int], Segment] = {}
        try:
            with session_scope() as session:
                for seg in session.query(Segment).all():
                    db_rows[(seg.song_id, seg.index)] = seg
        except Exception as e:
            logger.error("Failed to read segment DB rows: %s", e)
            return

        for song_dir in segments_dir.iterdir():
            if not song_dir.is_dir():
                continue
            song_id = song_dir.name
            for f in song_dir.iterdir():
                if not f.is_file():
                    continue
                if f.name.endswith(".tmp"):
                    try:
                        f.unlink()
                        orphans_deleted += 1
                    except OSError:
                        pass
                    continue

                if f.name == "init.bin":
                    index = -1
                else:
                    try:
                        index = int(f.stem)
                    except ValueError:
                        try:
                            f.unlink()
                            orphans_deleted += 1
                        except OSError:
                            pass
                        continue

                key = (song_id, index)
                row = db_rows.get(key)
                if row is None:
                    try:
                        f.unlink()
                        orphans_deleted += 1
                    except OSError:
                        pass
                else:
                    try:
                        actual_size = f.stat().st_size
                        if actual_size != row.size_bytes:
                            f.unlink()
                            with session_scope() as session:
                                s = session.get(Segment, key)
                                if s:
                                    session.delete(s)
                            mismatches_deleted += 1
                        else:
                            self.set_segment_status(song_id, index, SegmentStatus.DOWNLOADED)
                    except OSError:
                        pass

        # Delete DB rows with missing files
        for (song_id, index) in list(db_rows.keys()):
            path = self._segment_path(song_id, index)
            if not path.exists():
                try:
                    with session_scope() as session:
                        s = session.get(Segment, (song_id, index))
                        if s:
                            session.delete(s)
                    missing_deleted += 1
                except Exception:
                    pass

        logger.info(
            "Reconciliation done: %d orphans, %d missing, %d mismatches removed",
            orphans_deleted, missing_deleted, mismatches_deleted,
        )

    # --- Audio serving (Range support, §6.7, P16) ---

    def serve_audio_range(
        self,
        song_id: str,
        range_header: Optional[str] = None,
    ) -> Tuple[int, Dict[str, str], Any]:
        """Serve audio bytes with real HTTP Range support.

        Returns (status_code, headers, body).
        Body can be bytes (error) or a generator (audio data).
        """
        validate_song_id(song_id)
        info = self._get_stream_info(song_id)
        if not info:
            return 404, {}, b"Stream not available - could not extract audio URL (video may be unavailable, region-locked, or format not found)"

        total = info.total_bytes
        headers = {
            "Content-Type": info.mime_type,
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache",
        }

        if range_header is None:
            headers["Content-Length"] = str(total)
            return 200, headers, self._iter_full_audio(song_id, info)

        # Parse Range header
        m = re.match(r"bytes=(\d*)-(\d*)", range_header.strip())
        if not m:
            return 416, {**headers, "Content-Range": f"bytes */{total}"}, b"Invalid range"

        start_str, end_str = m.groups()
        if start_str == "" and end_str == "":
            return 416, {**headers, "Content-Range": f"bytes */{total}"}, b"Invalid range"

        if start_str == "":
            # Suffix range: bytes=-N (last N bytes)
            suffix_len = int(end_str)
            if suffix_len <= 0:
                return 416, {**headers, "Content-Range": f"bytes */{total}"}, b"Invalid suffix range"
            req_start = max(0, total - suffix_len)
            req_end = total - 1
        else:
            req_start = int(start_str)
            req_end = int(end_str) if end_str else total - 1
            req_end = min(req_end, total - 1)

        if req_start >= total or req_start > req_end:
            return 416, {**headers, "Content-Range": f"bytes */{total}"}, b"Range not satisfiable"

        length = req_end - req_start + 1
        headers["Content-Range"] = f"bytes {req_start}-{req_end}/{total}"
        headers["Content-Length"] = str(length)

        return 206, headers, self._iter_audio_range(song_id, info, req_start, req_end)

    def _iter_full_audio(self, song_id: str, info: StreamInfo) -> Iterator[bytes]:
        """Generator yielding the full audio file from segments."""
        layout = build_virtual_layout(info)
        for virt_start, virt_end, seg_index, file_offset in layout:
            path = self._segment_path(song_id, seg_index)
            if not path.exists():
                self.download_segment_sync(song_id, seg_index)
            if path.exists():
                yield from self._read_file_chunks(path)

    def _iter_audio_range(
        self, song_id: str, info: StreamInfo, req_start: int, req_end: int
    ) -> Iterator[bytes]:
        """Generator yielding bytes for [req_start, req_end] from the virtual layout."""
        layout = build_virtual_layout(info)
        reads = map_range_to_segments(layout, req_start, req_end)

        for virt_start, virt_end, seg_index, file_offset, read_start, read_end in reads:
            path = self._segment_path(song_id, seg_index)
            if not path.exists():
                self.download_segment_sync(song_id, seg_index)
            if path.exists():
                with open(path, "rb") as f:
                    f.seek(read_start)
                    remaining = read_end - read_start + 1
                    while remaining > 0:
                        chunk = f.read(min(65536, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk

    def _read_file_chunks(self, path: Path, chunk_size: int = 65536) -> Iterator[bytes]:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    # --- DB helpers ---

    def _get_song_title(self, song_id: str) -> str:
        try:
            from backend.database.models import Song
            with session_scope() as session:
                song = session.get(Song, song_id)
                return song.title if song else ""
        except Exception:
            return ""

    def _get_song_duration(self, song_id: str) -> int:
        try:
            from backend.database.models import Song
            with session_scope() as session:
                song = session.get(Song, song_id)
                return song.duration_ms if song else 0
        except Exception:
            return 0

    def get_stream_info_summary(self, song_id: str) -> Optional[Dict[str, Any]]:
        """Return a JSON-serializable summary of StreamInfo."""
        info = self._get_stream_info(song_id)
        if not info:
            return None
        return {
            "song_id": info.song_id,
            "title": info.title,
            "duration_ms": info.duration_ms,
            "mime_type": info.mime_type,
            "init_range": list(info.init_range),
            "total_bytes": info.total_bytes,
            "is_dash": info.is_dash,
            "segment_count": len(info.segments),
            "segments": [
                {
                    "index": s.index,
                    "byte_start": s.byte_start,
                    "byte_end": s.byte_end,
                    "duration_ms": s.duration_ms,
                }
                for s in info.segments
            ],
        }


# ---------------------------------------------------------------------------
# Exception types for retry classification
# ---------------------------------------------------------------------------


class _Auth403Error(Exception):
    """403 — triggers stream URL refresh (P4)."""


class _PermanentError(Exception):
    """Non-retryable error (other 4xx, range ignored, etc.)."""


class _TransientError(Exception):
    """Retryable error (429, 5xx, timeout, short read)."""


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: Optional[StreamingService] = None
_lock = threading.Lock()


def get_streaming_service() -> StreamingService:
    global _instance
    with _lock:
        if _instance is None:
            _instance = StreamingService()
        return _instance


def reset_streaming_service() -> None:
    global _instance
    with _lock:
        if _instance is not None:
            _instance.stop()
        _instance = None
