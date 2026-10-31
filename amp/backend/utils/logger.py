"""Logging: app.log + streaming.log file handlers plus an in-memory ring buffer.

The ring buffer is what the /api/stream/logs endpoint reads.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from pathlib import Path
from typing import Deque, List

from backend.config import settings

_RING_SIZE = 1000
_ring_lock = threading.Lock()
_ring: Deque[str] = deque(maxlen=_RING_SIZE)

_configured = False


class RingBufferHandler(logging.Handler):
    """Appends formatted records to the in-memory ring."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            with _ring_lock:
                _ring.append(msg)
        except Exception:
            self.handleError(record)


def get_ring_lines(n: int = 200) -> List[str]:
    with _ring_lock:
        lines = list(_ring)
    return lines[-n:]


def clear_ring() -> None:
    with _ring_lock:
        _ring.clear()


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File: app.log (everything)
    app_path = settings.logs_dir / "app.log"
    fh_app = logging.FileHandler(app_path, encoding="utf-8")
    fh_app.setFormatter(fmt)
    fh_app.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    root.addHandler(fh_app)

    # File: streaming.log (streaming namespace only)
    stream_path = settings.logs_dir / "streaming.log"
    fh_stream = logging.FileHandler(stream_path, encoding="utf-8")
    fh_stream.setFormatter(fmt)
    fh_stream.setLevel(logging.DEBUG)
    fh_stream.addFilter(lambda r: r.name.startswith((
        "backend.services.streaming", "backend.services.extractor", "backend.utils.layout", "backend.utils.mp4",
    )))
    root.addHandler(fh_stream)

    # In-memory ring
    ring = RingBufferHandler()
    ring.setFormatter(fmt)
    ring.setLevel(logging.INFO)
    root.addHandler(ring)

    # Quiet down noisy third-party loggers
    for noisy in ("yt_dlp", "ytmusicapi", "urllib3", "requests", "httpcore", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
