"""Streaming package — public API unchanged: `from backend.services.streaming import …`.

  service.py     StreamingService facade + singleton
  registry.py    SegmentRegistry — single source of truth for per-segment state
  downloader.py  DownloadManager (queue + workers) + fetch_segment()
  cache.py       CacheStore — paths, size accounting, LRU, reconciliation, layout.json
  serving.py     serve_audio_range() + byte iterators
  playback.py    PlaybackSession + buffer-ahead policy
"""

from backend.services.extractor import BoundedDict
from backend.services.streaming.cache import LAYOUT_MANIFEST, CacheStore
from backend.services.streaming.downloader import (
    DownloadManager,
    SegmentTask,
    _Auth403Error,
    _PermanentError,
    _TransientError,
    fetch_segment,
)
from backend.services.streaming.playback import PlaybackInfo, PlaybackSession, buffer_plan
from backend.services.streaming.registry import (
    Priority,
    SegEntry,
    SegmentRegistry,
    SegmentStatus,
    SegState,
)
from backend.services.streaming.serving import SegmentUnavailable
from backend.services.streaming.service import (
    SIDX_HEAD_BYTES,
    StreamingService,
    get_streaming_service,
    reset_streaming_service,
    validate_song_id,
)

__all__ = [
    "BoundedDict", "CacheStore", "DownloadManager", "LAYOUT_MANIFEST", "PlaybackInfo", "PlaybackSession",
    "Priority", "SIDX_HEAD_BYTES", "SegEntry", "SegState", "SegmentRegistry", "SegmentStatus", "SegmentTask",
    "SegmentUnavailable", "StreamingService", "_Auth403Error", "_PermanentError", "_TransientError",
    "buffer_plan", "fetch_segment", "get_streaming_service", "reset_streaming_service", "validate_song_id",
]
