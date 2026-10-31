"""Unit tests for services/streaming/downloader.py — DownloadManager + fetch_segment."""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from backend.services.streaming.downloader import (
    DownloadManager,
    SegmentTask,
    _Auth403Error,
    _PermanentError,
    _TransientError,
    fetch_segment,
)
from backend.services.streaming.registry import Priority, SegmentRegistry, SegState

SONG = "dQw4w9WgXcQ"


def _manager(handler, workers=1):
    registry = SegmentRegistry()
    dm = DownloadManager(registry, num_workers=workers)

    def complete(task):
        handler(task)
        registry.complete((task.song_id, task.index), True)

    dm.set_handler(complete)
    return dm, registry


def _drain(dm, registry, keys, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if all(registry.get(k) in (SegState.DONE, SegState.ERROR) for k in keys):
            return
        time.sleep(0.01)
    raise AssertionError("downloads did not finish")


class TestSegmentTask:
    def test_priority_ordering(self):
        assert SegmentTask(SONG, 0, Priority.CRITICAL, 0, seq=2) < SegmentTask(SONG, 1, Priority.NORMAL, 0, seq=1)

    def test_newer_epoch_first_within_priority(self):
        assert SegmentTask(SONG, 9, Priority.NORMAL, 1, seq=9) < SegmentTask(SONG, 1, Priority.NORMAL, 0, seq=1)

    def test_seq_tiebreaker(self):
        assert SegmentTask(SONG, 0, Priority.NORMAL, 0, seq=1) < SegmentTask(SONG, 1, Priority.NORMAL, 0, seq=2)


class TestDownloadManager:
    def test_enqueue_dedupes_through_registry(self):
        seen = []
        dm, registry = _manager(lambda t: seen.append(t.index))
        assert dm.enqueue(SONG, 0, Priority.CRITICAL, 0) is True
        assert dm.enqueue(SONG, 0, Priority.CRITICAL, 0) is False
        assert dm.enqueue(SONG, 1, Priority.NORMAL, 0) is True
        dm.start()
        try:
            _drain(dm, registry, [(SONG, 0), (SONG, 1)])
        finally:
            dm.stop()
        assert sorted(seen) == [0, 1]

    def test_priority_order(self):
        seen = []
        dm, registry = _manager(lambda t: seen.append(t.index))
        dm.enqueue(SONG, 0, Priority.NORMAL, 0)
        dm.enqueue(SONG, 1, Priority.HIGH, 0)
        dm.enqueue(SONG, 2, Priority.CRITICAL, 0)
        dm.start()
        try:
            _drain(dm, registry, [(SONG, i) for i in range(3)])
        finally:
            dm.stop()
        assert seen == [2, 1, 0]

    def test_seek_requeues_queued_segment(self):
        """F6: a queued segment re-requested by a seek is downloaded once, at the new rank."""
        seen = []
        dm, registry = _manager(lambda t: seen.append((t.index, t.priority, t.epoch)))
        for i in range(10):
            dm.enqueue(SONG, i, Priority.NORMAL, 0)
        assert dm.enqueue(SONG, 5, Priority.CRITICAL, 1) is True  # the seek
        dm.start()
        try:
            _drain(dm, registry, [(SONG, i) for i in range(10)])
        finally:
            dm.stop()
        assert seen[0] == (5, Priority.CRITICAL, 1)
        assert [i for i, _, _ in seen].count(5) == 1
        assert sorted(i for i, _, _ in seen) == list(range(10))

    def test_superseded_heap_item_skipped(self):
        calls = []
        dm, registry = _manager(lambda t: calls.append(t))
        dm.enqueue(SONG, 3, Priority.NORMAL, 0)
        dm.enqueue(SONG, 3, Priority.HIGH, 0)  # second heap item, same key
        assert dm.queue_size() == 2
        dm.start()
        try:
            _drain(dm, registry, [(SONG, 3)])
            time.sleep(0.1)
        finally:
            dm.stop()
        assert len(calls) == 1
        assert calls[0].priority == Priority.HIGH

    def test_unqueued_item_skipped(self):
        calls = []
        dm, registry = _manager(lambda t: calls.append(t))
        dm.enqueue(SONG, 0, Priority.NORMAL, 0)
        registry.unqueue(SONG)
        dm.start()
        try:
            time.sleep(0.2)
        finally:
            dm.stop()
        assert calls == []
        assert registry.get((SONG, 0)) == SegState.MISSING

    def test_handler_exception_marks_error(self):
        registry = SegmentRegistry()
        dm = DownloadManager(registry, num_workers=1)
        dm.set_handler(lambda t: (_ for _ in ()).throw(RuntimeError("kaboom")))
        dm.enqueue(SONG, 0, Priority.NORMAL, 0)
        dm.start()
        try:
            assert registry.wait((SONG, 0), 5) == SegState.ERROR
        finally:
            dm.stop()
        assert registry.error((SONG, 0)) == "kaboom"

    def test_stop(self):
        dm, _ = _manager(lambda t: None, workers=2)
        dm.start()
        dm.stop()
        assert dm._executor is None


# ---------------------------------------------------------------------------
# fetch_segment
# ---------------------------------------------------------------------------


def _resp(status=206, body=b"x" * 100, content_range="bytes 0-99/1000", delay=0.0):
    resp = MagicMock()
    resp.status_code = status
    resp.headers = {"Content-Range": content_range}

    def iter_content(chunk_size=65536):
        if delay:
            time.sleep(delay)
        for i in range(0, len(body), 10):
            yield body[i:i + 10]

    resp.iter_content.side_effect = iter_content
    return resp


TIMEOUT = (1.0, 1.0)


class TestFetchSegment:
    def test_writes_verified_bytes(self, tmp_path):
        http = MagicMock()
        http.get.return_value = _resp(body=bytes(range(100)))
        dest = tmp_path / SONG / "0000.bin"
        assert fetch_segment(http, "https://cdn/x", {}, 0, 99, dest, TIMEOUT) == 100
        assert dest.read_bytes() == bytes(range(100))
        assert http.get.call_args.kwargs["headers"]["Range"] == "bytes=0-99"
        assert list(dest.parent.glob("*.tmp")) == []

    @pytest.mark.parametrize("status, exc", [
        (403, _Auth403Error), (429, _TransientError), (503, _TransientError),
        (200, _PermanentError), (404, _PermanentError),
    ])
    def test_status_classification(self, tmp_path, status, exc):
        http = MagicMock()
        http.get.return_value = _resp(status=status)
        dest = tmp_path / "0000.bin"
        with pytest.raises(exc):
            fetch_segment(http, "https://cdn/x", {}, 0, 99, dest, TIMEOUT)
        assert not dest.exists()

    def test_content_range_mismatch(self, tmp_path):
        http = MagicMock()
        http.get.return_value = _resp(content_range="bytes 0-50/1000")
        with pytest.raises(_PermanentError):
            fetch_segment(http, "https://cdn/x", {}, 0, 99, tmp_path / "0000.bin", TIMEOUT)

    def test_short_read_leaves_no_files(self, tmp_path):
        http = MagicMock()
        http.get.return_value = _resp(body=b"x" * 60)
        with pytest.raises(_TransientError):
            fetch_segment(http, "https://cdn/x", {}, 0, 99, tmp_path / "0000.bin", TIMEOUT)
        assert list(tmp_path.iterdir()) == []

    def test_unique_tmp_names(self, tmp_path):
        """F8: two concurrent fetches of the same key never share a tmp path."""
        import tempfile as tempfile_mod

        real_mkstemp = tempfile_mod.mkstemp
        tmp_names = []

        def recording_mkstemp(*args, **kwargs):
            fd, name = real_mkstemp(*args, **kwargs)
            tmp_names.append(name)
            return fd, name

        http = MagicMock()
        http.get.side_effect = lambda *a, **kw: _resp(body=b"y" * 100, delay=0.1)
        dest = tmp_path / SONG / "0007.bin"
        errors = []

        def run():
            try:
                fetch_segment(http, "https://cdn/x", {}, 0, 99, dest, TIMEOUT)
            except Exception as e:  # pragma: no cover - would fail the test below
                errors.append(e)

        with patch("backend.services.streaming.downloader.tempfile.mkstemp", side_effect=recording_mkstemp):
            threads = [threading.Thread(target=run) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(5)
        assert not errors
        assert len(tmp_names) == 2 and tmp_names[0] != tmp_names[1]
        assert all(name.startswith(str(dest.parent)) for name in tmp_names)
        assert dest.read_bytes() == b"y" * 100
        assert list(dest.parent.glob("*.tmp")) == []
