"""Audio serving with real HTTP Range support (§6.7, P16) — never a short body (F7).

The first segment of a range is made available *before* the response headers
are returned, so a failure becomes a JSON error instead of a 206 that
promises bytes. A later segment that can't be delivered raises inside the
generator: Starlette aborts the connection, which the browser treats as a
retryable network error rather than a silently truncated file.

Handlers and these generators are synchronous on purpose (P21): they block on
ensure_segment(), which waits for a download, and Starlette runs sync handlers
and iterate_in_threadpool() in its threadpool (40 threads by default) — far
above 4 download workers plus the browser's 1–3 concurrent Range requests.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Protocol, Tuple

from backend.utils.layout import StreamInfo, build_virtual_layout, map_range_to_segments
from backend.utils.logger import get_logger

logger = get_logger("backend.services.streaming.serving")

CHUNK = 65536

# ExtractionError.code -> HTTP status for /audio
_EXTRACTION_STATUS = {
    "unavailable": 404,
    "no_audio": 404,
    "auth_required": 401,
    "node_missing": 503,
    "extract_failed": 502,
}


class SegmentUnavailable(Exception):
    """A segment could not be delivered within the timeout."""

    def __init__(self, song_id: str, index: int, reason: str) -> None:
        super().__init__(f"{song_id} seg {index}: {reason}")
        self.song_id, self.index, self.reason = song_id, index, reason


class SegmentSource(Protocol):
    def get_stream_info(self, song_id: str) -> Optional[StreamInfo]: ...
    def stream_error_code(self, song_id: str) -> Optional[str]: ...
    def ensure_segment(self, song_id: str, index: int, timeout: Optional[float] = None) -> Path: ...


def _error(status: int, code: str, detail: str) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
    return status, {"Content-Type": "application/json"}, {"detail": detail, "code": code}


def parse_range(range_header: Optional[str], total: int) -> Optional[Tuple[int, int]]:
    """'bytes=a-b' | 'bytes=a-' | 'bytes=-n' → inclusive (start, end); None if unsatisfiable."""
    if range_header is None:
        return 0, total - 1
    m = re.match(r"bytes=(\d*)-(\d*)", range_header.strip())
    if not m:
        return None
    start_str, end_str = m.groups()
    if start_str == "" and end_str == "":
        return None
    if start_str == "":
        suffix = int(end_str)  # last N bytes
        if suffix <= 0:
            return None
        start, end = max(0, total - suffix), total - 1
    else:
        start = int(start_str)
        end = min(int(end_str) if end_str else total - 1, total - 1)
    if start >= total or start > end:
        return None
    return start, end


def serve_audio_range(
    source: SegmentSource, song_id: str, range_header: Optional[str] = None,
) -> Tuple[int, Dict[str, str], Any]:
    """Returns (status, headers, body). body is a byte iterator for 200/206,
    a JSON-able dict for errors."""
    info = source.get_stream_info(song_id)
    if not info:
        code = source.stream_error_code(song_id) or "extract_failed"
        return _error(_EXTRACTION_STATUS.get(code, 502), code,
                      "Stream not available — could not extract an audio stream")

    total = info.total_bytes
    headers = {"Content-Type": info.mime_type, "Accept-Ranges": "bytes", "Cache-Control": "no-cache"}
    rng = parse_range(range_header, total)
    if rng is None:
        return 416, {**headers, "Content-Range": f"bytes */{total}"}, {"detail": "Range not satisfiable",
                                                                       "code": "bad_range"}
    start, end = rng
    reads = map_range_to_segments(build_virtual_layout(info), start, end)

    # First segment before any header promises bytes
    try:
        first = source.ensure_segment(song_id, reads[0][2])
    except SegmentUnavailable as e:
        logger.error("Audio %s: first segment unavailable: %s", song_id, e.reason)
        return _error(502, "segment_unavailable", str(e))

    headers["Content-Length"] = str(end - start + 1)
    if range_header is None:
        return 200, headers, _iter_reads(source, song_id, reads, first)
    headers["Content-Range"] = f"bytes {start}-{end}/{total}"
    return 206, headers, _iter_reads(source, song_id, reads, first)


def _iter_reads(source: SegmentSource, song_id: str, reads, first: Path) -> Iterator[bytes]:
    for n, (_, _, seg_index, _, read_start, read_end) in enumerate(reads):
        path = first if n == 0 else None
        yield from _read_segment(source, song_id, seg_index, read_start, read_end, path)


def _read_segment(
    source: SegmentSource, song_id: str, index: int, read_start: int, read_end: int, path: Optional[Path],
) -> Iterator[bytes]:
    for attempt in range(2):
        try:
            if path is None:
                path = source.ensure_segment(song_id, index)
            f = open(path, "rb")
        except SegmentUnavailable as e:
            logger.error("Audio %s: aborting response, segment %d unavailable: %s", song_id, index, e.reason)
            raise
        except FileNotFoundError:
            if attempt == 1:
                raise SegmentUnavailable(song_id, index, "file vanished twice") from None
            path = None  # evicted between ensure and open: fetch again
            continue
        with f:
            f.seek(read_start)
            remaining = read_end - read_start + 1
            while remaining > 0:
                chunk = f.read(min(CHUNK, remaining))
                if not chunk:
                    raise SegmentUnavailable(song_id, index, "file shorter than its byte range")
                remaining -= len(chunk)
                yield chunk
        return
