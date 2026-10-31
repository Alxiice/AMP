"""StreamExtractor — one yt-dlp extraction per song, however many callers ask.

Includes:
  - build_ydl_opts (option shapes yt-dlp actually honours, P2)
  - select_audio_format (pure: yt-dlp info dict -> ExtractedStream, audio-only)
  - SingleFlight (concurrent callers for a key share one computation)
  - StreamExtractor (positive + negative cache, client rotation, refresh per URL)

No FastAPI imports, no knowledge of segments.
"""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, List, Optional, Tuple, TypeVar
from urllib.parse import parse_qs, urlparse

from backend.config import settings
from backend.utils.logger import get_logger

logger = get_logger("backend.services.extractor")

# Some clients (e.g. TVHTML5) return URLs that 403 until a few seconds after
# extraction; yt-dlp exposes this as the format's available_at timestamp.
MAX_AVAILABLE_AT_WAIT_S = 30

# Expiry handling: treat URLs as stale this long before their expire= stamp
EXPIRY_MARGIN_S = 300
DEFAULT_URL_LIFETIME_S = 5 * 3600

# Negative cache TTLs per ExtractionError.code
FAILURE_TTL_S = {"unavailable": 30 * 60}
DEFAULT_FAILURE_TTL_S = 5 * 60

DEFAULT_CLIENT = "default"  # YTDLP_PLAYER_CLIENTS entry: leave player_client unset


def watch_url(song_id: str) -> str:
    return f"https://www.youtube.com/watch?v={song_id}"


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


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractedStream:
    song_id: str
    url: str                  # googlevideo URL — never log it (P24)
    itag: str
    ext: str                  # "m4a" | "webm" | "mp4" …
    mime_type: str            # "audio/mp4" | "audio/webm"
    acodec: str
    is_audio_only: bool
    filesize: Optional[int]   # bytes, from format["filesize"] or URL clen=
    duration_ms: int          # from info["duration"]; 0 if unknown
    title: str
    expires_at: float         # from URL expire=, minus a safety margin
    player_client: str        # which client succeeded (diagnostics)
    available_at: float = 0.0  # epoch seconds the URL goes live (0 = immediately)


class ExtractionError(Exception):
    """Extraction failed. code: unavailable | no_audio | auth_required | node_missing | extract_failed."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


# ---------------------------------------------------------------------------
# Bounded in-memory cache (P19) and single-flight
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


K = TypeVar("K")
V = TypeVar("V")


class SingleFlight(Generic[K, V]):
    """The first caller for a key runs fn; concurrent callers wait for its result.

    Every caller gets the same return value or the same exception. Once the
    flight lands the key is free again, so callers should re-check their cache
    inside fn.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._flights: Dict[K, Future] = {}

    def do(self, key: K, fn: Callable[[], V]) -> V:
        with self._lock:
            fut = self._flights.get(key)
            leader = fut is None
            if leader:
                fut = Future()
                self._flights[key] = fut
        if not leader:
            return fut.result()
        try:
            result = fn()
        except BaseException as e:
            fut.set_exception(e)
            raise
        else:
            fut.set_result(result)
            return result
        finally:
            with self._lock:
                self._flights.pop(key, None)


# ---------------------------------------------------------------------------
# Format selection (pure)
# ---------------------------------------------------------------------------

_MIME_BY_EXT = {"m4a": "audio/mp4", "mp4": "audio/mp4", "webm": "audio/webm"}


def _is_audio_only(f: Dict[str, Any]) -> bool:
    return f.get("vcodec") in (None, "none") and f.get("acodec") not in (None, "none")


def _bitrate(f: Dict[str, Any]) -> float:
    return f.get("abr") or f.get("tbr") or 0


def _query_param(url: str, name: str) -> Optional[str]:
    values = parse_qs(urlparse(url).query).get(name)
    return values[0] if values else None


def _int_param(url: str, name: str) -> Optional[int]:
    value = _query_param(url, name)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def select_audio_format(
    info: Dict[str, Any], song_id: str = "", player_client: str = DEFAULT_CLIENT,
) -> Optional[ExtractedStream]:
    """Pick the audio-only format to stream from a yt-dlp info dict.

    Preference: settings.STREAM_FORMAT itag > m4a/mp4 by bitrate > any audio-only
    (e.g. 251 webm/opus) by bitrate. Muxed video is never returned.
    """
    candidates = [f for f in info.get("formats") or [] if f.get("url") and _is_audio_only(f)]
    if not candidates:
        # Muxed video fallback (e.g. itag 18) is deliberately disabled: it
        # downloads video for an audio player. Uncomment only if ever wanted.
        # candidates = [f for f in info.get("formats") or []
        #               if f.get("url") and f.get("acodec") not in (None, "none")]
        return None

    preferred = [f for f in candidates if str(f.get("format_id")) == settings.STREAM_FORMAT]
    mp4 = sorted((f for f in candidates if f.get("ext") in ("m4a", "mp4")), key=_bitrate, reverse=True)
    fmt = (preferred or mp4 or sorted(candidates, key=_bitrate, reverse=True))[0]

    url = fmt["url"]
    ext = fmt.get("ext") or ""
    filesize = fmt.get("filesize") or _int_param(url, "clen")
    expire = _int_param(url, "expire")
    expires_at = expire - EXPIRY_MARGIN_S if expire else time.time() + DEFAULT_URL_LIFETIME_S
    duration = info.get("duration") or 0

    return ExtractedStream(
        song_id=song_id or info.get("id", ""),
        url=url,
        itag=str(fmt.get("format_id", "")),
        ext=ext,
        mime_type=_MIME_BY_EXT.get(ext, "audio/mp4"),
        acodec=fmt.get("acodec") or "",
        is_audio_only=True,
        filesize=int(filesize) if filesize else None,
        duration_ms=int(duration * 1000),
        title=info.get("title") or "",
        expires_at=float(expires_at),
        player_client=player_client,
        available_at=float(fmt.get("available_at") or 0),
    )


def classify_download_error(message: str) -> str:
    """Map yt-dlp DownloadError text to an ExtractionError code."""
    text = message.lower()
    if "video unavailable" in text or "private video" in text:
        return "unavailable"
    if any(s in text for s in ("sign in to confirm", "age-restricted", "age restricted", "inappropriate for some users")):
        return "auth_required"
    return "extract_failed"


def log_available_formats(song_id: str, info: Dict[str, Any], player_client: str) -> None:
    """Diagnostic: log the formats an extraction returned when none were usable."""
    formats = info.get("formats") or []
    if not formats:
        logger.warning(
            "Diagnostic for %s (client=%s): no formats returned (private, deleted, region-locked, or client blocked)",
            song_id, player_client,
        )
        return
    lines = [
        f"  itag={f.get('format_id', '?')} ext={f.get('ext', '?')} acodec={f.get('acodec', '?')} "
        f"vcodec={f.get('vcodec', '?')} abr={_bitrate(f)} url={'yes' if f.get('url') else 'NO'}"
        for f in formats
    ]
    logger.warning(
        "Diagnostic for %s (client=%s): %d formats, none audio-only with a URL:\n%s",
        song_id, player_client, len(formats), "\n".join(lines),
    )


def wait_until_available(stream: ExtractedStream) -> None:
    """Sleep until the stream URL is live (yt-dlp's available_at), capped."""
    if not stream.available_at:
        return
    delay = stream.available_at - time.time()
    if delay > 0:
        delay = min(delay, MAX_AVAILABLE_AT_WAIT_S)
        logger.info("Stream URL for %s not live yet, waiting %.1fs (available_at)", stream.song_id, delay)
        time.sleep(delay)


# ---------------------------------------------------------------------------
# Extraction prerequisites (P2)
# ---------------------------------------------------------------------------

_deps: Optional[Dict[str, Any]] = None
_deps_lock = threading.Lock()


def get_extraction_dependencies() -> Dict[str, Any]:
    """Return {"node": bool, "ejs": bool, "yt_dlp": version}; computed once, logged."""
    global _deps
    with _deps_lock:
        if _deps is not None:
            return _deps
        import importlib.util
        import shutil

        node = shutil.which("node")
        if node:
            logger.info("JS runtime: node found at %s", node)
        else:
            logger.warning("JS runtime: node NOT found on PATH — yt-dlp cannot solve YouTube JS challenges")

        ejs = importlib.util.find_spec("yt_dlp_ejs") is not None
        if ejs:
            logger.info("yt_dlp_ejs: importable")
        else:
            logger.warning('yt_dlp_ejs: NOT importable — install with: pip install -U "yt-dlp[default]"')

        try:
            from yt_dlp.version import __version__ as yt_dlp_version
        except Exception:
            yt_dlp_version = "unknown"
        logger.info("yt-dlp %s, player clients %s", yt_dlp_version, settings.YTDLP_PLAYER_CLIENTS)

        _deps = {"node": bool(node), "ejs": ejs, "yt_dlp": yt_dlp_version}
        return _deps


def _client_supports_cookies(client: Optional[str]) -> bool:
    """yt-dlp drops cookie-less clients (e.g. visionos) when a cookie file is passed."""
    if client is None:
        return True
    try:
        from yt_dlp.extractor.youtube._base import INNERTUBE_CLIENTS

        return bool(INNERTUBE_CLIENTS.get(client, {}).get("SUPPORTS_COOKIES", True))
    except Exception:
        return True


# ---------------------------------------------------------------------------
# StreamExtractor
# ---------------------------------------------------------------------------


class StreamExtractor:
    """Cached, single-flight yt-dlp extraction of one audio stream per song."""

    def __init__(self, auth: Any, dependencies: Optional[Dict[str, Any]] = None) -> None:
        self._auth = auth
        self._deps = dependencies
        self._streams: BoundedDict = BoundedDict(256)    # song_id -> ExtractedStream
        self._failures: BoundedDict = BoundedDict(256)   # song_id -> (failed_at, ExtractionError)
        self._flight: SingleFlight[str, ExtractedStream] = SingleFlight()

    # --- Public API ---

    def get(self, song_id: str) -> ExtractedStream:
        """Return a live stream for song_id, extracting at most once concurrently."""
        cached = self._fresh(song_id)
        if cached is not None:
            return cached
        self._raise_if_recently_failed(song_id)
        return self._flight.do(song_id, lambda: self._load(song_id))

    def refresh(self, song_id: str, stale_url: Optional[str] = None) -> ExtractedStream:
        """Re-extract after stale_url got a 403 (P4), once per URL generation.

        If the cached URL already differs from stale_url, another caller has
        refreshed it and that entry is returned. stale_url=None always refreshes.
        """
        def load() -> ExtractedStream:
            cached = self._fresh(song_id)
            if cached is not None and stale_url is not None and cached.url != stale_url:
                return cached
            previous = self._streams.get(song_id)
            self._streams.delete(song_id)
            self._failures.delete(song_id)
            stream = self._extract_and_store(song_id)
            if previous is not None and (previous.itag, previous.filesize) != (stream.itag, stream.filesize):
                logger.warning(
                    "Refreshed stream for %s changed layout: itag %s -> %s, filesize %s -> %s",
                    song_id, previous.itag, stream.itag, previous.filesize, stream.filesize,
                )
            return stream

        return self._flight.do(song_id, load)

    # --- Caches ---

    def _fresh(self, song_id: str) -> Optional[ExtractedStream]:
        stream = self._streams.get(song_id)
        if stream is not None and time.time() < stream.expires_at:
            return stream
        return None

    def _raise_if_recently_failed(self, song_id: str) -> None:
        entry = self._failures.get(song_id)
        if entry is None:
            return
        failed_at, error = entry
        if time.time() - failed_at < FAILURE_TTL_S.get(error.code, DEFAULT_FAILURE_TTL_S):
            raise error
        self._failures.delete(song_id)

    def _load(self, song_id: str) -> ExtractedStream:
        # Re-check: a flight that just landed may have filled either cache
        cached = self._fresh(song_id)
        if cached is not None:
            return cached
        self._raise_if_recently_failed(song_id)
        return self._extract_and_store(song_id)

    def _extract_and_store(self, song_id: str) -> ExtractedStream:
        try:
            stream = self._extract(song_id)
        except ExtractionError as e:
            if e.code != "node_missing":
                self._failures.set(song_id, (time.time(), e))
            raise
        self._streams.set(song_id, stream)
        return stream

    # --- yt-dlp ---

    def _dependencies(self) -> Dict[str, Any]:
        if self._deps is None:
            self._deps = get_extraction_dependencies()
        return self._deps

    def _extract(self, song_id: str) -> ExtractedStream:
        """Try each configured player client once; pick the format in Python."""
        if not self._dependencies().get("node"):
            raise ExtractionError("node_missing", "node is not on PATH; yt-dlp cannot solve YouTube JS challenges")

        clients: List[str] = list(settings.YTDLP_PLAYER_CLIENTS) or [DEFAULT_CLIENT]
        errors: List[Tuple[str, str]] = []  # (client, code)
        cookie_file = None
        try:
            if self._auth.is_authenticated:
                cookie_file = self._auth.write_netscape_cookie_file()

            for label in clients:
                client = None if label == DEFAULT_CLIENT else label
                # Cookie-less clients run anonymously rather than being dropped by yt-dlp
                cookies = cookie_file if _client_supports_cookies(client) else None
                try:
                    stream = self._extract_with_client(song_id, client, label, cookies)
                except ExtractionError as e:
                    errors.append((label, e.code))
                    if e.code == "unavailable":
                        raise
                    logger.warning("Extraction for %s with client=%s failed (%s): %s", song_id, label, e.code, e)
                    continue

                wait_until_available(stream)
                logger.info(
                    "Extracted stream for %s via client=%s: itag=%s %s %s, %s bytes, %.1fs",
                    song_id, label, stream.itag, stream.mime_type, stream.acodec,
                    stream.filesize, stream.duration_ms / 1000,
                )
                return stream
        finally:
            if cookie_file:
                try:
                    os.unlink(cookie_file)  # P23: always delete
                except OSError:
                    pass

        codes = {code for _, code in errors}
        code = next((c for c in ("auth_required", "no_audio") if c in codes), "extract_failed")
        logger.error("No stream for %s after %d client(s) %s: %s", song_id, len(clients), clients, code)
        raise ExtractionError(code, f"no audio stream for {song_id} ({code})")

    def _extract_with_client(
        self, song_id: str, client: Optional[str], label: str, cookie_file: Optional[str],
    ) -> ExtractedStream:
        from yt_dlp import YoutubeDL
        from yt_dlp.utils import DownloadError

        opts = build_ydl_opts(client, "bestaudio/best", cookie_file)
        # Warn instead of raising "Requested format is not available"; we choose in Python
        opts["ignore_no_formats_error"] = True
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(watch_url(song_id), download=False)
        except DownloadError as e:
            raise ExtractionError(classify_download_error(str(e)), str(e)) from e
        except Exception as e:
            raise ExtractionError("extract_failed", str(e)) from e

        if not info:
            raise ExtractionError("extract_failed", "yt-dlp returned no info")
        stream = select_audio_format(info, song_id, label)
        if stream is None:
            log_available_formats(song_id, info, label)
            raise ExtractionError("no_audio", "no audio-only format")
        return stream
