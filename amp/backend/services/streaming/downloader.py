"""DownloadManager (priority heap + worker threads) and fetch_segment (HTTP + verify + write).

The heap only carries hints: every item is checked against the SegmentRegistry
when popped, and skipped if it has been superseded (re-ranked, claimed by a
request handler, or unqueued).
"""

from __future__ import annotations

import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, PriorityQueue
from typing import Callable, Dict, Optional, Tuple

import requests

from backend.config import settings
from backend.services.streaming.cache import atomic_replace
from backend.services.streaming.registry import Priority, SegmentRegistry
from backend.utils.logger import get_logger

logger = get_logger("backend.services.streaming.downloader")


# ---------------------------------------------------------------------------
# Error classification for retries
# ---------------------------------------------------------------------------


class _Auth403Error(Exception):
    """403 — triggers stream URL refresh (P4)."""


class _PermanentError(Exception):
    """Non-retryable error (other 4xx, range ignored, etc.)."""


class _TransientError(Exception):
    """Retryable error (429, 5xx, timeout, short read)."""


# ---------------------------------------------------------------------------
# fetch_segment
# ---------------------------------------------------------------------------


def fetch_segment(
    http: requests.Session,
    url: str,
    headers: Dict[str, str],
    byte_start: int,
    byte_end: int,
    dest: Path,
    timeout: Tuple[float, float],
) -> int:
    """GET one byte range and write it to dest atomically. Returns the size.

    P14: status must be 206, Content-Range must match, byte count must match.
    P15: a uniquely named tmp file in dest's directory, fsync, os.replace — two
    concurrent fetches of the same segment never share a tmp path (F8).
    """
    if not url:
        raise _PermanentError("No URL for segment")
    expected = byte_end - byte_start + 1
    resp = http.get(
        url,
        headers={**headers, "Range": f"bytes={byte_start}-{byte_end}"},
        timeout=timeout,
        stream=True,
    )
    try:
        if resp.status_code == 403:
            raise _Auth403Error("403 Forbidden")
        if resp.status_code == 429:
            raise _TransientError("429 Too Many Requests")
        if resp.status_code >= 500:
            raise _TransientError(f"Server error {resp.status_code}")
        if resp.status_code == 200:
            raise _PermanentError("Server returned 200 (range ignored)")  # P14: never save
        if resp.status_code != 206:
            if 400 <= resp.status_code < 500:
                raise _PermanentError(f"Client error {resp.status_code}")
            raise _TransientError(f"Unexpected status {resp.status_code}")

        content_range = resp.headers.get("Content-Range", "")
        expected_cr = f"bytes {byte_start}-{byte_end}/"
        if not content_range.startswith(expected_cr):
            raise _PermanentError(f"Content-Range mismatch: {content_range!r} != {expected_cr!r}")

        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=f"{dest.stem}.", suffix=".tmp")
        try:
            received = 0
            with os.fdopen(fd, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        received += len(chunk)
                f.flush()
                os.fsync(f.fileno())
            if received != expected:
                raise _TransientError(f"Short read: {received} != {expected}")
            atomic_replace(tmp, dest, expected)
            tmp = None
            return received
        finally:
            if tmp is not None:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
    finally:
        resp.close()


# ---------------------------------------------------------------------------
# DownloadManager
# ---------------------------------------------------------------------------


@dataclass
class SegmentTask:
    """A heap item. (priority, epoch) must still match the registry when popped."""
    song_id: str
    index: int          # -1 = init segment
    priority: Priority
    epoch: int
    seq: int = 0        # tiebreaker for PriorityQueue

    def _rank(self) -> Tuple[int, int, int]:
        # Better priority first; within it, the newest epoch (a seek outranks
        # what was queued before it); then request order
        return (self.priority, -self.epoch, self.seq)

    def __lt__(self, other: "SegmentTask") -> bool:
        return self._rank() < other._rank()


class DownloadManager:
    """Priority queue + ThreadPoolExecutor; state lives in the SegmentRegistry."""

    def __init__(self, registry: SegmentRegistry, num_workers: Optional[int] = None) -> None:
        self._registry = registry
        self._workers = num_workers or settings.DOWNLOAD_WORKERS
        self._queue: PriorityQueue[SegmentTask] = PriorityQueue()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._seq = 0
        self._seq_lock = threading.Lock()
        self._shutdown = False
        self._task_handler: Optional[Callable[[SegmentTask], None]] = None

    def set_handler(self, handler: Callable[[SegmentTask], None]) -> None:
        """handler(task) runs after a successful claim and must complete the key."""
        self._task_handler = handler

    def start(self) -> None:
        if self._executor is not None:
            return
        self._shutdown = False
        self._executor = ThreadPoolExecutor(max_workers=self._workers, thread_name_prefix="dl-worker")
        for _ in range(self._workers):
            self._executor.submit(self._worker_loop)
        logger.info("DownloadManager started with %d workers", self._workers)

    def stop(self) -> None:
        self._shutdown = True
        for _ in range(self._workers):  # wake workers
            self._queue.put_nowait(SegmentTask("", -1, Priority.LOW, 0, seq=-1))
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
            try:
                if self._shutdown or task.seq == -1:  # sentinel
                    continue
                key = (task.song_id, task.index)
                if not self._registry.claim(key, task.priority, task.epoch):
                    continue  # superseded duplicate, claimed by a request handler, or unqueued
                try:
                    if self._task_handler is None:
                        raise RuntimeError("no task handler")
                    self._task_handler(task)
                except Exception as e:
                    logger.error("Worker error on %s seg %d: %s", task.song_id, task.index, e)
                    self._registry.complete(key, False, str(e))
            finally:
                self._queue.task_done()

    def enqueue(self, song_id: str, index: int, priority: Priority, epoch: int) -> bool:
        """Request a segment; pushes a heap item only if the registry says so."""
        if not self._registry.request((song_id, index), priority, epoch):
            return False
        with self._seq_lock:
            self._seq += 1
            seq = self._seq
        self._queue.put(SegmentTask(song_id, index, priority, epoch, seq))
        return True

    def queue_size(self) -> int:
        return self._queue.qsize()
