"""StreamingService — facade over the streaming pipeline (public API used by endpoints.py).

  - Stream info: StreamExtractor (services/extractor.py) → segment table
    (exact from the fMP4 sidx, utils/mp4.py; proportional for WebM / no sidx)
  - SegmentRegistry (registry.py): the only per-segment state
  - DownloadManager + fetch_segment (downloader.py)
  - CacheStore (cache.py): files, layout.json identity, LRU, reconciliation
  - serve_audio_range (serving.py), PlaybackSession + buffer-ahead (playback.py)
"""

from __future__ import annotations

import random
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from backend.config import settings
from backend.services.auth import get_auth_service
from backend.services.extractor import (
    BoundedDict,
    ExtractedStream,
    ExtractionError,
    SingleFlight,
    StreamExtractor,
)
from backend.services.streaming.cache import CacheStore
from backend.services.streaming.downloader import (
    DownloadManager,
    SegmentTask,
    _Auth403Error,
    _PermanentError,
    fetch_segment,
)
from backend.services.streaming.playback import PlaybackSession, buffer_plan
from backend.services.streaming.registry import SegmentRegistry, SegState, to_status
from backend.services.streaming.serving import SegmentUnavailable, serve_audio_range
from backend.utils.layout import (
    StreamInfo,
    SegmentInfo as DashSegmentInfo,
    position_ms_to_segment_index,
)
from backend.utils.logger import get_logger
from backend.utils.mp4 import NeedMoreData, parse_fmp4_index

logger = get_logger("backend.services.streaming")

# First request for an fMP4 stream: ftyp + moov + sidx are ~1-2 KB for YouTube audio
SIDX_HEAD_BYTES = 65536

# P13: song_id validation
SONG_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def validate_song_id(song_id: str) -> str:
    if not SONG_ID_RE.match(song_id):
        raise ValueError(f"Invalid song_id: {song_id!r}")
    return song_id


class StreamingService:
    """Thread-safe singleton: segment streaming, cache, playback session."""

    def __init__(self) -> None:
        self._auth = get_auth_service()
        self._extractor = StreamExtractor(self._auth)
        self._registry = SegmentRegistry()
        self._cache = CacheStore(self._registry)
        self._dl_manager = DownloadManager(self._registry)
        self._dl_manager.set_handler(self._process_task)
        self._playback = PlaybackSession()

        # Bounded in-memory caches (P19)
        self._stream_info_cache: BoundedDict = BoundedDict(256)
        self._stream_errors: BoundedDict = BoundedDict(256)   # song_id -> last ExtractionError code
        self._info_flight: SingleFlight[str, Optional[StreamInfo]] = SingleFlight()
        self._epochs: Dict[str, int] = {}
        self._epochs_lock = threading.Lock()

        # HTTP session for CDN requests
        self._http = requests.Session()

    # --- Lifecycle ---

    def start(self) -> None:
        self._dl_manager.start()
        self.reconcile_cache()

    def stop(self) -> None:
        self._dl_manager.stop()

    # --- Epochs: a seek's requests outrank what was queued before it ---

    def get_epoch(self, song_id: str) -> int:
        with self._epochs_lock:
            return self._epochs.get(song_id, 0)

    def bump_epoch(self, song_id: str) -> int:
        with self._epochs_lock:
            new_epoch = self._epochs.get(song_id, 0) + 1
            self._epochs[song_id] = new_epoch
        self._playback.set_epoch(song_id, new_epoch)
        logger.info("Epoch bumped for %s -> %d", song_id, new_epoch)
        return new_epoch

    # --- Playback session ---

    def start_playback(self, song_id: str) -> Dict[str, Any]:
        validate_song_id(song_id)
        epoch = self.get_epoch(song_id)
        self._playback.start(song_id, epoch)
        # Leftovers queued for other songs would compete with this one
        for other in self._registry.queued_songs():
            if other != song_id:
                self._registry.unqueue(other)
        self._queue_buffer_ahead(song_id, start_index=0, epoch=epoch)
        return {"message": "playback started", "song_id": song_id, "epoch": epoch}

    def pause_playback(self) -> Dict[str, Any]:
        self._playback.set_playing(False)
        return {"message": "paused"}

    def resume_playback(self) -> Dict[str, Any]:
        state = self._playback.set_playing(True)
        if state.song_id:
            self._queue_buffer_ahead(state.song_id, start_index=state.current_segment_index)
        return {"message": "resumed"}

    def stop_playback(self) -> Dict[str, Any]:
        song_id = self._playback.stop()
        if song_id:
            self._registry.unqueue(song_id)  # in-flight downloads finish; queued ones are dropped
        return {"message": "stopped"}

    def update_position(self, position_ms: int) -> Dict[str, Any]:
        song_id = self._playback.snapshot().song_id
        index = self._position_to_index(song_id, position_ms) if song_id else 0
        self._playback.set_position(position_ms, index)
        if song_id:
            self._queue_buffer_ahead(song_id, start_index=index)  # no-op within the same segment
        return {"message": "position updated", "position_ms": position_ms}

    def seek(self, position_ms: int) -> Dict[str, Any]:
        song_id = self._playback.snapshot().song_id
        if not song_id:
            return {"message": "no active song"}
        epoch = self.bump_epoch(song_id)
        start_index = self._position_to_index(song_id, position_ms)
        self._playback.set_position(position_ms, start_index, epoch)
        self._queue_buffer_ahead(song_id, start_index=start_index, epoch=epoch)
        return {"message": "seeked", "position_ms": position_ms, "segment_index": start_index, "epoch": epoch}

    def get_playback_state(self) -> Dict[str, Any]:
        return self._playback.snapshot().to_dict()

    def buffer_ahead(self, song_id: str) -> Dict[str, Any]:
        validate_song_id(song_id)
        state = self._playback.snapshot()
        start = state.current_segment_index if state.song_id == song_id else 0
        self._queue_buffer_ahead(song_id, start_index=start, force=True)
        return {"message": "buffer-ahead triggered", "song_id": song_id}

    def _position_to_index(self, song_id: str, position_ms: int) -> int:
        info = self._get_stream_info(song_id)
        if info and info.segments:
            return position_ms_to_segment_index(info, position_ms)
        return 0

    def _queue_buffer_ahead(
        self, song_id: str, start_index: int = 0, epoch: Optional[int] = None, force: bool = False,
    ) -> None:
        """Request init + segments around the playhead (playback.buffer_plan).

        Skipped when the last buffer-ahead started from the same segment and
        epoch, so 2 s position reports inside one segment do nothing.
        """
        if epoch is None:
            epoch = self.get_epoch(song_id)
        if not force and not self._playback.should_buffer(song_id, start_index, epoch):
            return
        info = self._get_stream_info(song_id)
        if not info:
            logger.warning("Cannot buffer-ahead: no stream info for %s", song_id)
            return
        for index, priority in buffer_plan(info, start_index, settings.SEGMENT_BUFFER_AHEAD_SEC * 1000):
            self._dl_manager.enqueue(song_id, index, priority, epoch)

    # --- Stream info (extraction + manifest/probe), single-flight per song ---

    def get_stream_info(self, song_id: str) -> Optional[StreamInfo]:
        validate_song_id(song_id)
        return self._get_stream_info(song_id)

    def _get_stream_info(self, song_id: str) -> Optional[StreamInfo]:
        cached = self._stream_info_cache.get(song_id)
        if cached is not None:
            return cached

        def load() -> Optional[StreamInfo]:
            # Re-check: a flight that just landed may have filled the cache
            cached = self._stream_info_cache.get(song_id)
            if cached is not None:
                return cached
            return self._store_stream_info(song_id, self._build_stream_info(song_id))

        try:
            info = self._info_flight.do(song_id, load)
            if info is not None:
                self._stream_errors.delete(song_id)
            return info
        except ExtractionError as e:
            logger.warning("No stream for %s: %s (%s)", song_id, e.code, e)
            self._stream_errors.set(song_id, e.code)
            return None
        except Exception as e:
            logger.error("Failed to build stream info for %s: %s", song_id, e)
            return None

    def _store_stream_info(self, song_id: str, info: Optional[StreamInfo]) -> Optional[StreamInfo]:
        if info:
            self._stream_info_cache.set(song_id, info)
        else:
            self._stream_info_cache.delete(song_id)
        return info

    def _build_stream_info(self, song_id: str) -> Optional[StreamInfo]:
        """Extract the stream (raises ExtractionError), then build its segment table."""
        return self._build_from_stream(song_id, self._extractor.get(song_id))

    def _build_from_stream(self, song_id: str, stream: ExtractedStream) -> Optional[StreamInfo]:
        """Exact table from the fMP4 sidx when possible, else a proportional split.

        Applies cache identity (layout.json) before returning, and caches the
        init segment from the head bytes already fetched.
        """
        headers = self._auth.get_cdn_headers()
        info: Optional[StreamInfo] = None
        head: Optional[bytes] = None
        if stream.ext in ("m4a", "mp4"):
            info, head = self._build_sidx_info(song_id, stream, headers)
        if info is None:
            info = self._build_proportional_info(song_id, stream, headers)
        if info is None:
            return None

        self._cache.apply_layout(info)
        if head is not None and info.has_init and len(head) > info.init_range[1]:
            self._cache_init_from_head(info, head)
        return info

    def _cache_init_from_head(self, info: StreamInfo, head: bytes) -> None:
        """The head fetch already covers [0, init_end]: store it as init.bin."""
        key = (info.song_id, -1)
        if not self._registry.claim(key):
            return  # already on disk, or being downloaded
        try:
            start, end = info.init_range
            self._cache.write_segment(info.song_id, -1, head[start:end + 1])
            self._cache.record_segment(info.song_id, -1, start, end, end - start + 1, 0, info.layout_id)
            self._registry.complete(key, True)
        except Exception as e:
            self._registry.complete(key, False, str(e))

    def _fetch_head(self, url: str, headers: Dict[str, str], length: int) -> Optional[bytes]:
        """GET bytes [0, length) — at most length bytes even if the CDN ignores Range."""
        try:
            resp = self._http.get(
                url,
                headers={**headers, "Range": f"bytes=0-{length - 1}"},
                timeout=(settings.HTTP_TIMEOUT_CONNECT_S, settings.HTTP_TIMEOUT_READ_S),
                stream=True,
            )
        except requests.RequestException as e:
            logger.warning("Head fetch failed: %s", e)
            return None
        try:
            if resp.status_code not in (200, 206):
                logger.warning("Head fetch returned HTTP %d", resp.status_code)
                return None
            chunks: List[bytes] = []
            received = 0
            for chunk in resp.iter_content(chunk_size=65536):
                chunks.append(chunk)
                received += len(chunk)
                if received >= length:
                    break
            return b"".join(chunks)[:length]
        finally:
            resp.close()

    def _build_sidx_info(
        self, song_id: str, stream: ExtractedStream, headers: Dict[str, str],
    ) -> Tuple[Optional[StreamInfo], Optional[bytes]]:
        """Read ftyp + moov + sidx from the file head → exact segment table."""
        length = SIDX_HEAD_BYTES
        for attempt in range(3):
            head = self._fetch_head(stream.url, headers, length)
            if head is None:
                return None, None
            try:
                index = parse_fmp4_index(head)
                break
            except NeedMoreData as e:
                # Big moov: re-fetch past the box we need, with room for the sidx.
                # A short read means the file ended, so there is no sidx to find.
                if attempt < 2 and len(head) == length and e.required_len > length:
                    length = e.required_len + SIDX_HEAD_BYTES
                    continue
                logger.warning("No complete sidx for %s in %d bytes; using proportional split", song_id, len(head))
                return None, None
            except ValueError as e:
                logger.warning("No usable sidx for %s (%s); using proportional split", song_id, e)
                return None, None

        if stream.filesize and index.total_bytes != stream.filesize:
            logger.warning(
                "sidx for %s covers %d bytes but the file has %d; using proportional split",
                song_id, index.total_bytes, stream.filesize,
            )
            return None, None
        if stream.duration_ms and abs(index.duration_ms - stream.duration_ms) > 1000:
            logger.warning(
                "sidx durations for %s sum to %d ms, extraction says %d ms",
                song_id, index.duration_ms, stream.duration_ms,
            )

        segments = [
            DashSegmentInfo(index=i, byte_start=start, byte_end=end, duration_ms=dur, url=stream.url)
            for i, (start, end, dur) in enumerate(index.segments)
        ]
        info = StreamInfo(
            song_id=song_id,
            title=stream.title,
            duration_ms=index.duration_ms,
            mime_type=stream.mime_type,
            init_range=(0, index.init_end),  # ftyp + moov + sidx: virtual file == CDN file
            segments=segments,
            is_dash=True,
            base_url=stream.url,
            itag=stream.itag,
        )
        logger.info(
            "Segment table for %s from sidx: %d segments, %d bytes, %.1fs, %s",
            song_id, len(segments), info.total_bytes, info.duration_ms / 1000, stream.mime_type,
        )
        return info, head

    def _build_proportional_info(
        self, song_id: str, stream: ExtractedStream, headers: Dict[str, str],
    ) -> Optional[StreamInfo]:
        """Fallback (WebM, or no sidx): proportional segments from the extracted size and duration."""
        url = stream.url
        total_bytes = stream.filesize or self._probe_content_length(url, headers)
        if total_bytes <= 0:
            logger.error("Cannot determine size for stream %s", song_id)
            return None

        duration_ms = stream.duration_ms
        if duration_ms <= 0:
            logger.error("Unknown duration for stream %s", song_id)
            return None

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
            title=stream.title,
            duration_ms=duration_ms,
            mime_type=stream.mime_type,
            init_range=(0, -1),  # no init segment — first segment starts at byte 0
            segments=segments,
            is_dash=False,
            base_url=url,
            itag=stream.itag,
        )
        logger.info(
            "Proportional segments for %s: %d segments, %d bytes, %.1fs, %s",
            song_id, len(segments), total_bytes, duration_ms / 1000, stream.mime_type,
        )
        return info

    def _probe_content_length(self, url: str, headers: Dict[str, str]) -> int:
        """P5: content length when extraction didn't provide it. Returns 0 on failure."""
        # Strategy 1: HEAD
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

        # Strategy 2: Range probe bytes=0-0
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

    def refresh_stream_url(self, song_id: str, stale_url: Optional[str] = None) -> Optional[str]:
        """Re-extract the stream URL (P4: on 403); once per stale URL."""
        try:
            return self._extractor.refresh(song_id, stale_url).url
        except ExtractionError as e:
            logger.warning("Refresh failed for %s: %s (%s)", song_id, e.code, e)
            return None

    # --- Segment status (/chunks, from memory) ---

    def get_segment_status(self, song_id: str, index: int) -> SegState:
        return self._registry.get((song_id, index))

    def get_all_segment_statuses(self, song_id: str) -> List[Dict[str, Any]]:
        """Segment status list for the SegmentBar — registry only, no filesystem calls."""
        info = self._get_stream_info(song_id)
        if not info:
            return []
        states = self._registry.snapshot(song_id)
        result = []
        if info.has_init:
            result.append({
                "index": -1,
                "status": to_status(states.get(-1, SegState.MISSING)).value,
                "duration_ms": 0,
                "size_bytes": info.init_size,
            })
        for seg in info.segments:
            result.append({
                "index": seg.index,
                "status": to_status(states.get(seg.index, SegState.MISSING)).value,
                "duration_ms": seg.duration_ms,
                "size_bytes": seg.byte_end - seg.byte_start + 1,
            })
        return result

    # --- Segment download (§6.5) ---

    def ensure_segment(self, song_id: str, index: int, timeout: Optional[float] = None) -> Path:
        """Return the segment's path, downloading it in this thread if nobody else is.

        DONE → path. IN_FLIGHT elsewhere → wait for it. QUEUED / MISSING / ERROR →
        claim it and fetch here (jumps the queue; the queued heap item is then
        skipped). Raises SegmentUnavailable on failure or timeout.
        """
        if timeout is None:
            timeout = settings.SEGMENT_SYNC_TIMEOUT_S
        key = (song_id, index)
        path = self._cache.segment_path(song_id, index)
        state = self._registry.get(key)
        if state == SegState.DONE:
            if path.exists():
                self._cache.touch(path)
                return path
            self._registry.evicted(key)  # file vanished
        if self._registry.claim(key):
            self._run_download(song_id, index)
        state = self._registry.wait(key, timeout)
        if state == SegState.DONE:
            self._cache.touch(path)
            return path
        reason = self._registry.error(key) if state == SegState.ERROR else f"not ready after {timeout:.0f}s"
        raise SegmentUnavailable(song_id, index, reason or state.value)

    def _process_task(self, task: SegmentTask) -> None:
        """Worker callback, called after the worker claimed the key."""
        self._run_download(task.song_id, task.index)

    def _run_download(self, song_id: str, index: int) -> None:
        """Download a claimed (IN_FLIGHT) segment and always complete its key."""
        key = (song_id, index)
        try:
            ok, error, info = self._download_segment_with_retry(song_id, index)
            if ok and info is not None:
                current = self._stream_info_cache.get(song_id)
                if current is not None and current.layout_id != info.layout_id:
                    # The layout changed while we downloaded: these bytes belong to the old one
                    self._cache.remove_segment(song_id, index)
                    ok, error = False, "layout changed during download"
        except Exception as e:
            ok, error = False, str(e)
        if not ok:
            logger.error("Download failed for %s seg %d: %s", song_id, index, error)
        self._registry.complete(key, ok, error)
        if ok:
            self._cache.maybe_evict(self._playback.protected())

    @staticmethod
    def _segment_range(info: StreamInfo, index: int) -> Optional[Tuple[int, int, int]]:
        """(byte_start, byte_end, duration_ms) of a segment, None if not in the table."""
        if index == -1:
            return (info.init_range[0], info.init_range[1], 0) if info.has_init else None
        if 0 <= index < len(info.segments):
            seg = info.segments[index]
            return seg.byte_start, seg.byte_end, seg.duration_ms
        return None

    def _download_segment_with_retry(
        self, song_id: str, index: int,
    ) -> Tuple[bool, Optional[str], Optional[StreamInfo]]:
        """Fetch with retries (§6.5 step 6). Returns (ok, error, info used)."""
        info = self._get_stream_info(song_id)
        if not info:
            return False, "no stream info", None
        refreshed = False
        error: Optional[str] = None
        for attempt in range(settings.MAX_RETRIES):
            rng = self._segment_range(info, index)
            if rng is None:
                return False, f"segment {index} not in the segment table", info
            byte_start, byte_end, duration_ms = rng
            try:
                size = fetch_segment(
                    self._http, info.base_url, self._auth.get_cdn_headers(), byte_start, byte_end,
                    self._cache.segment_path(song_id, index),
                    (settings.HTTP_TIMEOUT_CONNECT_S, settings.HTTP_TIMEOUT_READ_S),
                )
            except _Auth403Error:
                # P4: the signed URL expired — not the YouTube session, so auth state
                # is untouched and the refresh still extracts with cookies. Passing the
                # URL that got the 403 lets concurrent workers share one re-extraction.
                if refreshed:
                    return False, "403 after refreshing the stream URL", info
                refreshed = True
                logger.warning("403 on %s seg %d, refreshing stream URL", song_id, index)
                new_info = self._rebuild_after_403(song_id, info.base_url)
                if new_info is None:
                    return False, "stream URL refresh failed", info
                info = new_info
                continue
            except _PermanentError as e:
                return False, str(e), info
            except Exception as e:
                error = str(e)
                logger.warning("Attempt %d/%d failed for %s seg %d: %s",
                               attempt + 1, settings.MAX_RETRIES, song_id, index, e)
            else:
                self._cache.record_segment(song_id, index, byte_start, byte_end, size, duration_ms, info.layout_id)
                return True, None, info

            if attempt < settings.MAX_RETRIES - 1:
                backoff = [0.5, 1.0, 2.0][min(attempt, 2)]
                jitter = random.uniform(0, 0.3)  # noqa: S311 - backoff jitter, not crypto
                time.sleep(backoff + jitter)

        return False, error or f"all {settings.MAX_RETRIES} attempts failed", info

    def _rebuild_after_403(self, song_id: str, stale_url: str) -> Optional[StreamInfo]:
        """Refresh stream URL and rebuild segment table (P4), once per stale URL."""
        def load() -> Optional[StreamInfo]:
            cached = self._stream_info_cache.get(song_id)
            if cached is not None and cached.base_url != stale_url:
                return cached  # another worker already rebuilt it
            stream = self._extractor.refresh(song_id, stale_url)
            return self._store_stream_info(song_id, self._build_from_stream(song_id, stream))

        try:
            return self._info_flight.do(song_id, load)
        except ExtractionError as e:
            logger.warning("Refresh failed for %s: %s (%s)", song_id, e.code, e)
            self._stream_errors.set(song_id, e.code)
            self._store_stream_info(song_id, None)
            return None

    # --- Cache management (§6.6) ---

    def cleanup_cache(self) -> None:
        """Full rescan + LRU eviction (the per-download check is incremental)."""
        try:
            self._cache.rescan()
            self._cache.maybe_evict(self._playback.protected())
        except Exception as e:
            logger.error("Cache cleanup failed: %s", e)

    def reconcile_cache(self) -> None:
        """Startup reconciliation: heal crash damage, rebuild the registry (§6.6)."""
        self._cache.reconcile()

    def get_cache_info(self) -> Dict[str, Any]:
        return self._cache.info()

    # --- Audio serving (Range support, §6.7, P16) ---

    def serve_audio_range(self, song_id: str, range_header: Optional[str] = None) -> Tuple[int, Dict[str, str], Any]:
        validate_song_id(song_id)
        return serve_audio_range(self, song_id, range_header)

    def stream_error_code(self, song_id: str) -> Optional[str]:
        """Last ExtractionError code for the song, if its stream info failed."""
        return self._stream_errors.get(song_id)

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
            "is_dash": info.is_dash,  # True = exact segment table (sidx), False = proportional
            "method": info.method,
            "itag": info.itag,
            "layout_id": info.layout_id,
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
