"""PlaybackSession (in-memory, one current song) and the buffer-ahead policy."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional, Tuple

from backend.services.streaming.registry import Priority
from backend.utils.layout import StreamInfo


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


def buffer_plan(info: StreamInfo, start_index: int, window_ms: int) -> List[Tuple[int, Priority]]:
    """Segments to request around the playhead, in order.

    init (if any) and the playhead segment CRITICAL, the next 2 HIGH, then
    NORMAL until window_ms past the playhead is covered (relative to the
    playhead, not the song start).
    """
    plan: List[Tuple[int, Priority]] = []
    if info.has_init:
        plan.append((-1, Priority.CRITICAL))
    ahead_ms = 0
    for idx in range(max(0, start_index), len(info.segments)):
        offset = idx - start_index
        if offset == 0:
            pri = Priority.CRITICAL
        elif offset <= 2:
            pri = Priority.HIGH
        elif ahead_ms > window_ms:
            break
        else:
            pri = Priority.NORMAL
        plan.append((idx, pri))
        ahead_ms += info.segments[idx].duration_ms
    return plan


class PlaybackSession:
    """Thread-safe holder of the current PlaybackInfo.

    last_buffered_index remembers the segment the last buffer-ahead started
    from, so position reports inside the same segment do nothing.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._info = PlaybackInfo()
        self._last_buffered: Optional[Tuple[str, int, int]] = None  # (song_id, index, epoch)

    def snapshot(self) -> PlaybackInfo:
        with self._lock:
            return replace(self._info)

    def start(self, song_id: str, epoch: int) -> None:
        with self._lock:
            self._info = PlaybackInfo(song_id=song_id, is_playing=True, epoch=epoch, last_updated=time.time())
            self._last_buffered = None

    def stop(self) -> str:
        with self._lock:
            song_id = self._info.song_id
            self._info = PlaybackInfo()
            self._last_buffered = None
            return song_id

    def set_playing(self, playing: bool) -> PlaybackInfo:
        with self._lock:
            self._info.is_playing = playing
            self._info.last_updated = time.time()
            return replace(self._info)

    def set_position(self, position_ms: int, segment_index: int, epoch: Optional[int] = None) -> None:
        with self._lock:
            self._info.position_ms = position_ms
            self._info.current_segment_index = segment_index
            self._info.last_updated = time.time()
            if epoch is not None:
                self._info.epoch = epoch

    def set_epoch(self, song_id: str, epoch: int) -> None:
        with self._lock:
            if self._info.song_id == song_id:
                self._info.epoch = epoch

    def should_buffer(self, song_id: str, index: int, epoch: int) -> bool:
        """True (and remembered) unless the last buffer-ahead had the same start."""
        key = (song_id, index, epoch)
        with self._lock:
            if self._last_buffered == key:
                return False
            self._last_buffered = key
            return True

    def protected(self) -> Optional[Tuple[str, int]]:
        """(song_id, current index) for cache eviction, or None when idle."""
        with self._lock:
            if not self._info.song_id:
                return None
            return self._info.song_id, self._info.current_segment_index
