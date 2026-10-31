"""Unit tests for services/streaming.py — DownloadManager, StreamingService.

Fully mocked, no network.
"""

import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from backend.services.streaming import (
    BoundedDict,
    DownloadManager,
    PlaybackInfo,
    Priority,
    SegmentStatus,
    SegmentTask,
    StreamingService,
    validate_song_id,
)


# ---------------------------------------------------------------------------
# song_id validation (P13)
# ---------------------------------------------------------------------------


class TestValidateSongId:
    def test_valid_ids(self):
        assert validate_song_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        assert validate_song_id("LTDxBgP0lqA") == "LTDxBgP0lqA"
        assert validate_song_id("abc-def_123") == "abc-def_123"

    def test_invalid_too_short(self):
        with pytest.raises(ValueError):
            validate_song_id("short")

    def test_invalid_too_long(self):
        with pytest.raises(ValueError):
            validate_song_id("dQw4w9WgXcQ12")  # 12 chars

    def test_invalid_characters(self):
        with pytest.raises(ValueError):
            validate_song_id("dQw4w9WgXc!")  # 11 chars but has !

    def test_path_traversal_blocked(self):
        with pytest.raises(ValueError):
            validate_song_id("../../etc/pwd")


# ---------------------------------------------------------------------------
# BoundedDict (P19)
# ---------------------------------------------------------------------------


class TestBoundedDict:
    def test_basic_set_get(self):
        d = BoundedDict(3)
        d.set("a", 1)
        assert d.get("a") == 1

    def test_eviction(self):
        d = BoundedDict(3)
        d.set("a", 1)
        d.set("b", 2)
        d.set("c", 3)
        d.set("d", 4)  # should evict "a"
        assert d.get("a") is None
        assert d.get("d") == 4
        assert len(d) == 3

    def test_update_existing(self):
        d = BoundedDict(3)
        d.set("a", 1)
        d.set("b", 2)
        d.set("a", 10)  # update, not evict
        assert d.get("a") == 10
        assert len(d) == 2

    def test_delete(self):
        d = BoundedDict(3)
        d.set("a", 1)
        d.delete("a")
        assert d.get("a") is None
        assert len(d) == 0

    def test_clear(self):
        d = BoundedDict(3)
        d.set("a", 1)
        d.set("b", 2)
        d.clear()
        assert len(d) == 0

    def test_contains(self):
        d = BoundedDict(3)
        d.set("a", 1)
        assert "a" in d
        assert "b" not in d


# ---------------------------------------------------------------------------
# SegmentTask priority
# ---------------------------------------------------------------------------


class TestSegmentTask:
    def test_priority_ordering(self):
        t1 = SegmentTask("song", 0, Priority.CRITICAL, 0, seq=1)
        t2 = SegmentTask("song", 1, Priority.NORMAL, 0, seq=2)
        assert t1 < t2  # CRITICAL < NORMAL

    def test_seq_tiebreaker(self):
        t1 = SegmentTask("song", 0, Priority.NORMAL, 0, seq=1)
        t2 = SegmentTask("song", 1, Priority.NORMAL, 0, seq=2)
        assert t1 < t2


# ---------------------------------------------------------------------------
# DownloadManager
# ---------------------------------------------------------------------------


class TestDownloadManager:
    def test_enqueue_and_dedupe(self):
        dm = DownloadManager(num_workers=1)
        processed = []
        dm.set_handler(lambda task: processed.append(task))
        dm.start()
        try:
            # Enqueue same segment twice — second should be deduped
            assert dm.enqueue("song1", 0, Priority.CRITICAL, 0) is True
            assert dm.enqueue("song1", 0, Priority.CRITICAL, 0) is False

            # Different segment should succeed
            assert dm.enqueue("song1", 1, Priority.NORMAL, 0) is True

            # Wait for processing
            time.sleep(0.5)
            assert len(processed) == 2
        finally:
            dm.stop()

    def test_priority_order(self):
        dm = DownloadManager(num_workers=1)
        processed = []
        dm.set_handler(lambda task: processed.append(task.index))
        dm.start()
        try:
            # Enqueue in reverse priority order
            dm.enqueue("song1", 0, Priority.NORMAL, 0)
            dm.enqueue("song1", 1, Priority.HIGH, 0)
            dm.enqueue("song1", 2, Priority.CRITICAL, 0)

            time.sleep(0.5)
            # Should be processed in priority order: CRITICAL(2), HIGH(1), NORMAL(0)
            assert processed == [2, 1, 0]
        finally:
            dm.stop()

    def test_is_downloading(self):
        dm = DownloadManager(num_workers=1)
        # Block the handler so we can check is_downloading
        import threading
        block = threading.Event()
        dm.set_handler(lambda task: block.wait(timeout=5))
        dm.start()
        try:
            dm.enqueue("song1", 0, Priority.CRITICAL, 0)
            time.sleep(0.1)  # let worker pick it up
            assert dm.is_downloading("song1", 0) is True
            block.set()  # release
            time.sleep(0.2)
            assert dm.is_downloading("song1", 0) is False
        finally:
            block.set()
            dm.stop()

    def test_stop(self):
        dm = DownloadManager(num_workers=2)
        dm.set_handler(lambda task: None)
        dm.start()
        dm.stop()
        assert dm._executor is None


# ---------------------------------------------------------------------------
# PlaybackInfo
# ---------------------------------------------------------------------------


class TestPlaybackInfo:
    def test_to_dict(self):
        info = PlaybackInfo(
            song_id="test", position_ms=5000, is_playing=True,
            volume=0.8, epoch=3, last_updated=1234.5,
        )
        d = info.to_dict()
        assert d["song_id"] == "test"
        assert d["position_ms"] == 5000
        assert d["is_playing"] is True
        assert d["volume"] == 0.8
        assert d["epoch"] == 3


# ---------------------------------------------------------------------------
# StreamingService — epoch management (P18)
# ---------------------------------------------------------------------------


class TestEpochManagement:
    def test_initial_epoch(self, temp_dirs):
        svc = StreamingService()
        assert svc.get_epoch("song1") == 0

    def test_bump_epoch(self, temp_dirs):
        svc = StreamingService()
        assert svc.bump_epoch("song1") == 1
        assert svc.get_epoch("song1") == 1
        assert svc.bump_epoch("song1") == 2
        assert svc.get_epoch("song1") == 2

    def test_independent_epochs(self, temp_dirs):
        svc = StreamingService()
        svc.bump_epoch("song1")
        svc.bump_epoch("song1")
        assert svc.get_epoch("song2") == 0  # independent
        svc.bump_epoch("song2")
        assert svc.get_epoch("song1") == 2
        assert svc.get_epoch("song2") == 1


# ---------------------------------------------------------------------------
# StreamingService — segment paths
# ---------------------------------------------------------------------------


class TestSegmentPaths:
    def test_init_path(self, temp_dirs):
        from backend.config import settings
        svc = StreamingService()
        path = svc._segment_path("dQw4w9WgXcQ", -1)
        assert path.name == "init.bin"
        assert path.parent.name == "dQw4w9WgXcQ"

    def test_segment_path(self, temp_dirs):
        svc = StreamingService()
        path = svc._segment_path("dQw4w9WgXcQ", 5)
        assert path.name == "0005.bin"

    def test_segment_path_zero_padded(self, temp_dirs):
        svc = StreamingService()
        path = svc._segment_path("dQw4w9WgXcQ", 0)
        assert path.name == "0000.bin"


# ---------------------------------------------------------------------------
# StreamingService — atomic write (P15)
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_atomic_write(self, temp_dirs):
        svc = StreamingService()
        data = b"\x00\x01\x02\x03" * 1000
        svc._atomic_write_segment("dQw4w9WgXcQ", 0, data)
        path = svc._segment_path("dQw4w9WgXcQ", 0)
        assert path.exists()
        assert path.read_bytes() == data
        # No .tmp file should remain
        assert not path.with_suffix(".tmp").exists()

    def test_atomic_write_init(self, temp_dirs):
        svc = StreamingService()
        data = b"\xff\xfe" * 500
        svc._atomic_write_segment("dQw4w9WgXcQ", -1, data)
        path = svc._segment_path("dQw4w9WgXcQ", -1)
        assert path.exists()
        assert path.read_bytes() == data


# ---------------------------------------------------------------------------
# StreamingService — segment status
# ---------------------------------------------------------------------------


class TestSegmentStatus:
    def test_default_pending(self, temp_dirs):
        svc = StreamingService()
        assert svc.get_segment_status("song1", 0) == SegmentStatus.PENDING

    def test_set_and_get(self, temp_dirs):
        svc = StreamingService()
        svc.set_segment_status("song1", 0, SegmentStatus.DOWNLOADING)
        assert svc.get_segment_status("song1", 0) == SegmentStatus.DOWNLOADING

    def test_independent_per_song(self, temp_dirs):
        svc = StreamingService()
        svc.set_segment_status("song1", 0, SegmentStatus.DOWNLOADED)
        assert svc.get_segment_status("song2", 0) == SegmentStatus.PENDING


# ---------------------------------------------------------------------------
# StreamingService — cache reconciliation
# ---------------------------------------------------------------------------


class TestCacheReconciliation:
    def test_reconcile_empty(self, temp_dirs):
        """Reconciliation on empty cache should not error."""
        svc = StreamingService()
        svc.reconcile_cache()  # should not raise

    def test_reconcile_orphan_file(self, temp_dirs):
        """Orphan files (no DB row) should be deleted."""
        from backend.config import settings
        song_dir = settings.segments_dir / "dQw4w9WgXcQ"
        song_dir.mkdir(parents=True)
        orphan = song_dir / "0000.bin"
        orphan.write_bytes(b"orphan data")

        svc = StreamingService()
        svc.reconcile_cache()
        assert not orphan.exists()

    def test_reconcile_tmp_files_deleted(self, temp_dirs):
        """Leftover .tmp files from crashed downloads should be deleted."""
        from backend.config import settings
        song_dir = settings.segments_dir / "dQw4w9WgXcQ"
        song_dir.mkdir(parents=True)
        tmp = song_dir / "0000.bin.tmp"
        tmp.write_bytes(b"partial")

        svc = StreamingService()
        svc.reconcile_cache()
        assert not tmp.exists()


# ---------------------------------------------------------------------------
# StreamingService — LRU cache eviction
# ---------------------------------------------------------------------------


class TestCacheEviction:
    def test_eviction_under_limit(self, temp_dirs):
        """No eviction when under the limit."""
        from backend.config import settings
        song_dir = settings.segments_dir / "dQw4w9WgXcQ"
        song_dir.mkdir(parents=True)
        (song_dir / "0000.bin").write_bytes(b"\x00" * 100)

        svc = StreamingService()
        svc.cleanup_cache()  # should not evict (under 1MB limit)
        assert (song_dir / "0000.bin").exists()

    def test_eviction_over_limit(self, temp_dirs):
        """Eviction when over the limit."""
        from backend.config import settings
        # Create two songs with files exceeding 1MB total
        for song_id in ["songAAAAAAA1", "songBBBBBBB2"]:
            song_dir = settings.segments_dir / song_id
            song_dir.mkdir(parents=True)
            (song_dir / "0000.bin").write_bytes(b"\x00" * 600_000)  # 600KB each = 1.2MB total

        svc = StreamingService()
        svc.cleanup_cache()

        # After eviction, total should be <= 80% of 1MB = 800KB
        total = sum(
            f.stat().st_size
            for song_dir in settings.segments_dir.iterdir()
            if song_dir.is_dir()
            for f in song_dir.iterdir()
            if f.is_file()
        )
        assert total <= 800_000


# ---------------------------------------------------------------------------
# CDN 403 handling (F9) and buffer-ahead window (F10)
# ---------------------------------------------------------------------------


def _make_stream_info(song_id, n_segments, seg_ms=5000, url="https://cdn.example.com/a"):
    from backend.utils.layout import SegmentInfo, StreamInfo

    seg_bytes = 1000
    segments = [
        SegmentInfo(index=i, byte_start=100 + i * seg_bytes, byte_end=100 + (i + 1) * seg_bytes - 1,
                    duration_ms=seg_ms, url=url)
        for i in range(n_segments)
    ]
    return StreamInfo(
        song_id=song_id, title="t", duration_ms=n_segments * seg_ms, mime_type="audio/mp4",
        init_range=(0, 99), segments=segments, base_url=url,
    )


def _extracted(song_id="dQw4w9WgXcQ", url="https://cdn.example.com/a", **kw):
    from backend.services.extractor import ExtractedStream

    fields = dict(
        song_id=song_id, url=url, itag="140", ext="m4a", mime_type="audio/mp4",
        acodec="mp4a.40.2", is_audio_only=True, filesize=None, duration_ms=180_000,
        title="t", expires_at=time.time() + 3600, player_client="default",
    )
    fields.update(kw)
    return ExtractedStream(**fields)


class TestCdn403:
    def test_403_does_not_change_auth_state(self, temp_dirs):
        from backend.services.auth import AuthState, get_auth_service
        from backend.services.streaming import _Auth403Error

        song_id = "dQw4w9WgXcQ"
        auth = get_auth_service()
        auth.set_cookies({"__Secure-3PAPISID": "abc", "SID": "def"})
        assert auth.state == AuthState.SIGNED_IN

        svc = StreamingService()
        svc._stream_info_cache.set(song_id, _make_stream_info(song_id, 3))
        svc._extractor._deps = {"node": True}
        states = []
        cookie_files = []

        def attempt(*args, **kwargs):
            states.append(auth.state)
            if len(states) == 1:
                raise _Auth403Error("403 Forbidden")
            return True

        def extract_with_client(sid, client, label, cookie_file):
            states.append(auth.state)
            cookie_files.append(cookie_file)
            return _extracted(sid, url="https://cdn.example.com/fresh")

        fresh = _make_stream_info(song_id, 3, url="https://cdn.example.com/fresh")
        with patch("backend.config.settings.YTDLP_PLAYER_CLIENTS", ["default"]), \
             patch.object(svc, "_download_segment_attempt", side_effect=attempt), \
             patch.object(svc._extractor, "_extract_with_client", side_effect=extract_with_client), \
             patch.object(svc, "_build_from_stream", return_value=fresh):
            svc._download_segment_with_retry(song_id, 0, svc.get_epoch(song_id))

        assert svc.get_segment_status(song_id, 0) == SegmentStatus.DOWNLOADED
        assert len(states) == 3  # 403 attempt, refresh extraction, retry attempt
        assert all(s == AuthState.SIGNED_IN for s in states)
        assert auth.state == AuthState.SIGNED_IN
        assert cookie_files and cookie_files[0] is not None

    def test_concurrent_403s_rebuild_once(self, temp_dirs):
        """4 workers hitting a 403 on the same URL cause one re-extraction (P4)."""
        import threading

        song_id = "dQw4w9WgXcQ"
        svc = StreamingService()
        stale = _make_stream_info(song_id, 3, url="https://cdn.example.com/old")
        svc._stream_info_cache.set(song_id, stale)
        gate = threading.Event()

        def refresh(sid, stale_url):
            gate.wait(2)
            return _extracted(sid, url="https://cdn.example.com/new")

        fresh = _make_stream_info(song_id, 3, url="https://cdn.example.com/new")
        results = []
        with patch.object(svc._extractor, "refresh", side_effect=refresh) as refresh_mock, \
             patch.object(svc, "_build_from_stream", return_value=fresh):
            threads = [threading.Thread(target=lambda: results.append(
                svc._rebuild_after_403(song_id, "https://cdn.example.com/old"))) for _ in range(4)]
            for t in threads:
                t.start()
            time.sleep(0.2)
            gate.set()
            for t in threads:
                t.join(5)
            # A late worker with the same stale URL reuses the rebuilt table
            results.append(svc._rebuild_after_403(song_id, "https://cdn.example.com/old"))

        assert refresh_mock.call_count == 1
        assert len(results) == 5 and all(r is fresh for r in results)


class TestStreamInfo:
    """Proportional fallback (WebM, or no sidx): real size + duration, no network."""

    def test_stream_info_uses_extracted_duration(self, temp_dirs, monkeypatch):
        from backend.config import settings

        monkeypatch.setattr(settings, "SEGMENT_TARGET_SEC", 5)
        song_id = "dQw4w9WgXcQ"
        svc = StreamingService()
        stream = _extracted(song_id, duration_ms=245_000, filesize=245 * 16_000,
                            mime_type="audio/webm", ext="webm", itag="251", title="Real title")
        with patch.object(svc._extractor, "get", return_value=stream),              patch.object(svc._http, "get") as http_get,              patch.object(svc, "_probe_content_length") as probe:
            info = svc.get_stream_info(song_id)

        probe.assert_not_called()  # filesize came from extraction
        http_get.assert_not_called()  # webm: no sidx head fetch
        assert info.is_dash is False
        assert info.duration_ms == 245_000
        assert len(info.segments) == 49
        assert abs(sum(s.duration_ms for s in info.segments) - 245_000) < 50
        assert info.total_bytes == 245 * 16_000
        assert info.mime_type == "audio/webm"
        assert info.title == "Real title"

    def test_probe_only_when_filesize_unknown(self, temp_dirs):
        song_id = "dQw4w9WgXcQ"
        svc = StreamingService()
        stream = _extracted(song_id, filesize=None, ext="webm", mime_type="audio/webm", itag="251")
        with patch.object(svc._extractor, "get", return_value=stream),              patch.object(svc, "_probe_content_length", return_value=2_880_000) as probe:
            info = svc.get_stream_info(song_id)
        probe.assert_called_once()
        assert info.total_bytes == 2_880_000

    def test_unknown_duration_gives_no_info(self, temp_dirs):
        song_id = "dQw4w9WgXcQ"
        svc = StreamingService()
        stream = _extracted(song_id, duration_ms=0, filesize=1000, ext="webm")
        with patch.object(svc._extractor, "get", return_value=stream):
            assert svc.get_stream_info(song_id) is None  # no 180 s fallback

    def test_stream_info_single_flight(self, temp_dirs):
        import threading

        song_id = "dQw4w9WgXcQ"
        svc = StreamingService()
        gate = threading.Event()
        info = _make_stream_info(song_id, 3)

        def build(sid):
            gate.wait(2)
            return info

        results = []
        with patch.object(svc, "_build_stream_info", side_effect=build) as build_mock:
            threads = [threading.Thread(target=lambda: results.append(svc.get_stream_info(song_id)))
                       for _ in range(10)]
            for t in threads:
                t.start()
            time.sleep(0.2)
            gate.set()
            for t in threads:
                t.join(5)

        assert build_mock.call_count == 1
        assert len(results) == 10 and all(r is info for r in results)

    def test_extraction_error_gives_no_info(self, temp_dirs):
        from backend.services.extractor import ExtractionError

        svc = StreamingService()
        with patch.object(svc._extractor, "get", side_effect=ExtractionError("unavailable")):
            assert svc.get_stream_info("dQw4w9WgXcQ") is None

class TestBufferAhead:
    def test_buffer_ahead_relative_to_playhead(self, temp_dirs, monkeypatch):
        from backend.config import settings

        monkeypatch.setattr(settings, "SEGMENT_BUFFER_AHEAD_SEC", 30)
        song_id = "dQw4w9WgXcQ"
        svc = StreamingService()
        svc._stream_info_cache.set(song_id, _make_stream_info(song_id, 60))
        svc._dl_manager = MagicMock()

        svc._queue_buffer_ahead(song_id, start_index=40, epoch=0)

        queued = [(c.args[1], c.args[2]) for c in svc._dl_manager.enqueue.call_args_list]
        assert queued == [
            (-1, Priority.CRITICAL),
            (40, Priority.CRITICAL),
            (41, Priority.HIGH),
            (42, Priority.HIGH),
            (43, Priority.NORMAL),
            (44, Priority.NORMAL),
            (45, Priority.NORMAL),
            (46, Priority.NORMAL),
        ]

    def test_buffer_ahead_stops_at_last_segment(self, temp_dirs):
        song_id = "dQw4w9WgXcQ"
        svc = StreamingService()
        svc._stream_info_cache.set(song_id, _make_stream_info(song_id, 60))
        svc._dl_manager = MagicMock()

        svc._queue_buffer_ahead(song_id, start_index=58, epoch=0)

        indices = [c.args[1] for c in svc._dl_manager.enqueue.call_args_list]
        assert indices == [-1, 58, 59]




# ---------------------------------------------------------------------------
# Exact segment table from the fMP4 sidx + cache identity (Phase 2)
# ---------------------------------------------------------------------------

FIXTURE_HEAD = Path(__file__).parent / "fixtures" / "itag140_head.bin"
FIXTURE_FILESIZE = 4_172_237


def _cdn_response(body: bytes, status: int = 206):
    resp = MagicMock()
    resp.status_code = status
    resp.headers = {}
    resp.iter_content.side_effect = lambda chunk_size=65536: iter(
        [body[i:i + chunk_size] for i in range(0, len(body), chunk_size)])
    return resp


def _sidx_stream(song_id="BAgTQhR8MLo", **kw):
    fields = dict(filesize=FIXTURE_FILESIZE, duration_ms=258_000, url="https://cdn.example.com/140")
    fields.update(kw)
    return _extracted(song_id, **fields)


def _build(svc, stream, *bodies):
    """Build stream info with the CDN head fetch(es) answered by bodies."""
    responses = [_cdn_response(b) for b in bodies]
    with patch.object(svc._extractor, "get", return_value=stream), \
         patch.object(svc._http, "get", side_effect=responses) as http_get:
        info = svc.get_stream_info(stream.song_id)
    return info, http_get


class TestSidxTable:
    def test_exact_table_from_sidx(self, temp_dirs):
        head = FIXTURE_HEAD.read_bytes()
        svc = StreamingService()
        info, http_get = _build(svc, _sidx_stream(), head + b"\0" * (65536 - len(head)))

        assert http_get.call_count == 1
        assert http_get.call_args.kwargs["headers"]["Range"] == "bytes=0-65535"
        assert info.is_dash is True
        assert info.method == "sidx"
        assert info.init_range == (0, len(head) - 1)
        assert len(info.segments) == 26
        assert info.total_bytes == FIXTURE_FILESIZE
        assert abs(info.duration_ms - 258_000) <= 1000
        assert info.itag == "140"

        # Head bytes already cover the init segment: cached as init.bin
        init = svc._segment_path("BAgTQhR8MLo", -1)
        assert init.read_bytes() == head
        assert svc.get_segment_status("BAgTQhR8MLo", -1) == SegmentStatus.DOWNLOADED

        manifest = json.loads(svc._layout_path("BAgTQhR8MLo").read_text())
        assert manifest["layout_id"] == info.layout_id
        assert manifest["method"] == "sidx"
        assert manifest["total_bytes"] == FIXTURE_FILESIZE
        assert len(manifest["segments"]) == 26

    def test_position_maps_to_exact_segment(self, temp_dirs):
        from backend.utils.layout import position_ms_to_segment_index

        head = FIXTURE_HEAD.read_bytes()
        svc = StreamingService()
        info, _ = _build(svc, _sidx_stream(), head)
        # 50 %: the segment whose [start, end) contains 129 s
        target = info.duration_ms // 2
        idx = position_ms_to_segment_index(info, target)
        start = sum(s.duration_ms for s in info.segments[:idx])
        assert start <= target < start + info.segments[idx].duration_ms

    def test_need_more_data_refetches(self, temp_dirs):
        from backend.tests.test_mp4 import fmp4_head

        refs = [(10_000, 441_000)] * 3  # 3 x 10 s
        head = fmp4_head(refs, moov_len=70_000)  # moov alone is past the first 64 KB
        sidx_end = len(head) - 16  # minus the trailing moof box
        stream = _sidx_stream("dQw4w9WgXcQ", filesize=sidx_end + 30_000, duration_ms=30_000)
        svc = StreamingService()
        info, http_get = _build(svc, stream, head[:65536], head)

        assert http_get.call_count == 2
        moov_end = 24 + 70_008
        second = http_get.call_args_list[1].kwargs["headers"]["Range"]
        assert second == f"bytes=0-{moov_end + 8 + 65536 - 1}"  # next header + room for the sidx
        assert info.is_dash is True
        assert info.init_range == (0, sidx_end - 1)
        assert len(info.segments) == 3

    def test_short_file_without_sidx_does_not_loop(self, temp_dirs):
        from backend.tests.test_mp4 import box

        head = box(b"ftyp", b"x" * 8) + box(b"moov", bytes(20))  # file ends, no sidx
        svc = StreamingService()
        info, http_get = _build(svc, _sidx_stream(filesize=500_000, duration_ms=30_000), head)
        assert http_get.call_count == 1
        assert info.is_dash is False

    def test_filesize_mismatch_falls_back(self, temp_dirs):
        head = FIXTURE_HEAD.read_bytes()
        svc = StreamingService()
        info, _ = _build(svc, _sidx_stream(filesize=FIXTURE_FILESIZE + 1), head)
        assert info.is_dash is False
        assert not svc._segment_path("BAgTQhR8MLo", -1).exists()

    def test_no_sidx_falls_back(self, temp_dirs):
        from backend.tests.test_mp4 import box

        head = box(b"ftyp", b"x" * 8) + box(b"moov", b"\0" * 20) + box(b"moof", b"\0" * 8)
        svc = StreamingService()
        info, _ = _build(svc, _sidx_stream(filesize=500_000, duration_ms=30_000), head)
        assert info.is_dash is False

    def test_head_http_error_falls_back(self, temp_dirs):
        svc = StreamingService()
        with patch.object(svc._extractor, "get", return_value=_sidx_stream()), \
             patch.object(svc._http, "get", return_value=_cdn_response(b"", status=403)):
            info = svc.get_stream_info("BAgTQhR8MLo")
        assert info.is_dash is False


class TestLayoutIdentity:
    def test_layout_change_purges_song(self, temp_dirs):
        from backend.config import settings

        song_id = "BAgTQhR8MLo"
        svc = StreamingService()
        # Layout A: proportional (e.g. an earlier itag 251 extraction)
        info_a = svc._build_from_stream(song_id, _extracted(
            song_id, ext="webm", itag="251", mime_type="audio/webm", filesize=4_000_000, duration_ms=258_000))
        svc._atomic_write_segment(song_id, 0, b"old layout bytes")
        svc._record_segment_db(song_id, 0, 0, 15, 16, 5000, info_a.layout_id)
        svc.set_segment_status(song_id, 0, SegmentStatus.DOWNLOADED)

        # Layout B: sidx
        head = FIXTURE_HEAD.read_bytes()
        with patch.object(svc._http, "get", return_value=_cdn_response(head)):
            info_b = svc._build_from_stream(song_id, _sidx_stream())

        assert info_b.layout_id != info_a.layout_id
        assert not svc._segment_path(song_id, 0).exists()
        assert svc.get_segment_status(song_id, 0) == SegmentStatus.PENDING
        assert svc._read_layout_id(song_id) == info_b.layout_id
        assert svc._segment_path(song_id, -1).exists()  # new init cached after the purge
        from backend.database.models import Segment
        from backend.database.session import session_scope
        with session_scope() as session:
            assert session.get(Segment, (song_id, 0)) is None
        assert (settings.segments_dir / song_id).is_dir()

    def test_same_layout_keeps_cache(self, temp_dirs):
        song_id = "BAgTQhR8MLo"
        svc = StreamingService()
        stream = _extracted(song_id, ext="webm", itag="251", filesize=4_000_000, duration_ms=258_000)
        info = svc._build_from_stream(song_id, stream)
        svc._atomic_write_segment(song_id, 0, b"keep me")
        assert svc._build_from_stream(song_id, stream).layout_id == info.layout_id
        assert svc._segment_path(song_id, 0).read_bytes() == b"keep me"

    def test_reconcile_deletes_dir_without_manifest(self, temp_dirs):
        from backend.config import settings

        legacy = settings.segments_dir / "dQw4w9WgXcQ"
        legacy.mkdir(parents=True)
        (legacy / "0000.bin").write_bytes(b"pre-phase-2 proportional segment")
        svc = StreamingService()
        svc._record_segment_db("dQw4w9WgXcQ", 0, 0, 31, 32, 5000, None)
        svc.reconcile_cache()
        assert not legacy.exists()
        from backend.database.models import Segment
        from backend.database.session import session_scope
        with session_scope() as session:
            assert session.get(Segment, ("dQw4w9WgXcQ", 0)) is None

    def test_reconcile_keeps_matching_and_drops_foreign_layout_rows(self, temp_dirs):
        song_id = "BAgTQhR8MLo"
        svc = StreamingService()
        info = svc._build_from_stream(song_id, _extracted(
            song_id, ext="webm", itag="251", filesize=4_000_000, duration_ms=258_000))
        svc._atomic_write_segment(song_id, 0, b"a" * 10)
        svc._record_segment_db(song_id, 0, 0, 9, 10, 5000, info.layout_id)
        svc._atomic_write_segment(song_id, 1, b"b" * 10)
        svc._record_segment_db(song_id, 1, 10, 19, 10, 5000, "someotherlayout0")

        fresh = StreamingService()
        fresh.reconcile_cache()
        assert svc._segment_path(song_id, 0).exists()
        assert fresh.get_segment_status(song_id, 0) == SegmentStatus.DOWNLOADED
        assert not svc._segment_path(song_id, 1).exists()
        assert svc._layout_path(song_id).exists()

    def test_manifest_not_counted_or_evicted(self, temp_dirs):
        song_id = "BAgTQhR8MLo"
        svc = StreamingService()
        svc._build_from_stream(song_id, _extracted(
            song_id, ext="webm", itag="251", filesize=4_000_000, duration_ms=258_000))
        info = svc.get_cache_info()
        assert info["file_count"] == 0
        svc._atomic_write_segment(song_id, 0, b"\0" * 1_200_000)  # over the 1 MB test limit
        svc.cleanup_cache()
        assert svc._layout_path(song_id).exists()


class TestSegmentsTableMigration:
    def test_old_segments_table_recreated(self, temp_dirs):
        from sqlalchemy import inspect, text

        import backend.database.session as session_mod

        engine = session_mod.get_engine()
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE segments"))
            conn.execute(text(
                "CREATE TABLE segments (song_id VARCHAR(32), \"index\" INTEGER, byte_start INTEGER, "
                "byte_end INTEGER, size_bytes INTEGER, duration_ms INTEGER, status VARCHAR(16), "
                "file_path TEXT, last_accessed DATETIME, PRIMARY KEY (song_id, \"index\"))"))
            conn.execute(text("INSERT INTO segments (song_id, \"index\") VALUES ('dQw4w9WgXcQ', 0)"))
        session_mod.init_db()
        cols = {c["name"] for c in inspect(engine).get_columns("segments")}
        assert "layout_id" in cols
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM segments")).scalar() == 0
