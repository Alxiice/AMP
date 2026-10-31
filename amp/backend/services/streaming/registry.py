"""SegmentRegistry — the single source of truth for per-segment download state.

One lock guards every (song_id, index) entry. Workers, request handlers and
the cache all go through it, so "queued", "in flight" and "on disk" can't
disagree (F6, F8).
"""

from __future__ import annotations

import enum
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

Key = Tuple[str, int]  # (song_id, index); index -1 = init segment


class Priority(int, enum.Enum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


class SegState(str, enum.Enum):
    MISSING = "missing"
    QUEUED = "queued"
    IN_FLIGHT = "in_flight"
    DONE = "done"
    ERROR = "error"


class SegmentStatus(str, enum.Enum):
    """Status names reported by /chunks (SegmentBar)."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    ERROR = "error"


_STATUS = {
    SegState.MISSING: SegmentStatus.PENDING,
    SegState.QUEUED: SegmentStatus.PENDING,
    SegState.IN_FLIGHT: SegmentStatus.DOWNLOADING,
    SegState.DONE: SegmentStatus.DOWNLOADED,
    SegState.ERROR: SegmentStatus.ERROR,
}


def to_status(state: SegState) -> SegmentStatus:
    return _STATUS[state]


@dataclass
class SegEntry:
    state: SegState = SegState.MISSING
    priority: Optional[Priority] = None   # best priority requested while QUEUED
    epoch: int = 0
    done: threading.Event = field(default_factory=threading.Event)  # set on DONE or ERROR
    error: Optional[str] = None


class SegmentRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._songs: Dict[str, Dict[int, SegEntry]] = {}

    def _entry(self, key: Key) -> SegEntry:
        song_id, index = key
        return self._songs.setdefault(song_id, {}).setdefault(index, SegEntry())

    def get(self, key: Key) -> SegState:
        with self._lock:
            entry = self._songs.get(key[0], {}).get(key[1])
            return entry.state if entry else SegState.MISSING

    def error(self, key: Key) -> Optional[str]:
        with self._lock:
            entry = self._songs.get(key[0], {}).get(key[1])
            return entry.error if entry else None

    def request(self, key: Key, priority: Priority, epoch: int) -> bool:
        """Ask for a segment. True if the caller should push a new heap item.

        DONE / IN_FLIGHT: nothing to do. QUEUED: re-rank if the request is from a
        newer epoch or has a better priority in the same epoch (the old heap item
        becomes a superseded duplicate). MISSING / ERROR: queue it.
        """
        with self._lock:
            e = self._entry(key)
            if e.state in (SegState.DONE, SegState.IN_FLIGHT):
                return False
            if e.state == SegState.QUEUED:
                if epoch > e.epoch or (epoch == e.epoch and priority < e.priority):
                    e.priority, e.epoch = priority, epoch
                    return True
                return False
            e.state, e.priority, e.epoch, e.error = SegState.QUEUED, priority, epoch, None
            e.done.clear()
            return True

    def claim(self, key: Key, priority: Optional[Priority] = None, epoch: Optional[int] = None) -> bool:
        """Take ownership of a download (→ IN_FLIGHT).

        Workers pass the (priority, epoch) of their heap item: the claim only
        succeeds if that item is still the current one. Request handlers pass
        nothing and may claim any segment that isn't DONE or IN_FLIGHT, jumping
        the queue.
        """
        with self._lock:
            e = self._entry(key)
            if priority is not None:
                if e.state != SegState.QUEUED or (e.priority, e.epoch) != (priority, epoch):
                    return False
            elif e.state in (SegState.DONE, SegState.IN_FLIGHT):
                return False
            e.state, e.error = SegState.IN_FLIGHT, None
            e.done.clear()
            return True

    def complete(self, key: Key, ok: bool, error: Optional[str] = None) -> None:
        """IN_FLIGHT → DONE | ERROR, waking every waiter."""
        with self._lock:
            e = self._entry(key)
            e.state = SegState.DONE if ok else SegState.ERROR
            e.priority = None
            e.error = None if ok else (error or "download failed")
            e.done.set()

    def mark_done(self, key: Key) -> None:
        """A file is already on disk (startup reconciliation, init from the head fetch)."""
        self.complete(key, True)

    def evicted(self, key: Key) -> None:
        """DONE → MISSING after the file was deleted."""
        with self._lock:
            entry = self._songs.get(key[0], {}).get(key[1])
            if entry is not None and entry.state == SegState.DONE:
                entry.state = SegState.MISSING
                entry.done.clear()

    def unqueue(self, song_id: str) -> int:
        """QUEUED → MISSING for one song; their heap items are skipped when popped."""
        with self._lock:
            n = 0
            for entry in self._songs.get(song_id, {}).values():
                if entry.state == SegState.QUEUED:
                    entry.state, entry.priority = SegState.MISSING, None
                    n += 1
            return n

    def queued_songs(self) -> list[str]:
        with self._lock:
            return [s for s, entries in self._songs.items()
                    if any(e.state == SegState.QUEUED for e in entries.values())]

    def forget(self, song_id: str) -> None:
        """Drop a song's entries (cache purged). In-flight entries stay so their
        owners can still complete them and wake their waiters."""
        with self._lock:
            entries = self._songs.get(song_id)
            if not entries:
                return
            for index in [i for i, e in entries.items() if e.state != SegState.IN_FLIGHT]:
                del entries[index]
            if not entries:
                del self._songs[song_id]

    def wait(self, key: Key, timeout: float) -> SegState:
        """Block until the segment is DONE or ERROR (or timeout); return its state."""
        with self._lock:
            event = self._entry(key).done
        event.wait(timeout)
        return self.get(key)

    def snapshot(self, song_id: str) -> Dict[int, SegState]:
        with self._lock:
            return {i: e.state for i, e in self._songs.get(song_id, {}).items()}

    def is_in_flight(self, key: Key) -> bool:
        return self.get(key) == SegState.IN_FLIGHT
