"""Unit tests for services/streaming/cache.py — CacheStore paths, accounting, LRU."""

import os
import time

from backend.services.streaming.cache import (
    LAYOUT_MANIFEST,
    CacheStore,
    atomic_replace,
    parse_segment_name,
)
from backend.services.streaming.registry import SegmentRegistry, SegState

SONG = "dQw4w9WgXcQ"
OTHER = "BAgTQhR8MLo"


def _store():
    registry = SegmentRegistry()
    return CacheStore(registry), registry


def _put(store, registry, song_id, index, size, mtime=None):
    """Write + record a segment the way a download would."""
    path = store.write_segment(song_id, index, b"\0" * size)
    store.record_segment(song_id, index, 0, size - 1, size, 5000, "layout0000000000")
    registry.mark_done((song_id, index))
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def _scan_total(store):
    from backend.config import settings
    return sum(f.stat().st_size for d in settings.segments_dir.iterdir() if d.is_dir()
               for f in d.iterdir() if parse_segment_name(f.name) is not None)


class TestPaths:
    def test_segment_paths(self, temp_dirs):
        store, _ = _store()
        assert store.segment_path(SONG, -1).name == "init.bin"
        assert store.segment_path(SONG, 5).name == "0005.bin"
        assert store.segment_path(SONG, 0).parent.name == SONG
        assert store.layout_path(SONG).name == LAYOUT_MANIFEST

    def test_parse_segment_name(self):
        assert parse_segment_name("init.bin") == -1
        assert parse_segment_name("0012.bin") == 12
        assert parse_segment_name("0012.bin.tmp") is None
        assert parse_segment_name("0012.k3j4.tmp") is None
        assert parse_segment_name(LAYOUT_MANIFEST) is None


class TestWrites:
    def test_atomic_write(self, temp_dirs):
        store, _ = _store()
        data = b"\x00\x01\x02\x03" * 1000
        path = store.write_segment(SONG, 0, data)
        assert path.read_bytes() == data
        assert list(path.parent.glob("*.tmp")) == []

    def test_atomic_replace_tolerates_identical_winner(self, tmp_path, monkeypatch):
        dest = tmp_path / "0000.bin"
        dest.write_bytes(b"a" * 10)
        tmp = tmp_path / "0000.x.tmp"
        tmp.write_bytes(b"a" * 10)

        def locked(src, dst):
            raise PermissionError(13, "in use")

        monkeypatch.setattr("backend.services.streaming.cache.os.replace", locked)
        atomic_replace(str(tmp), dest, 10)
        assert not tmp.exists()
        assert dest.read_bytes() == b"a" * 10

    def test_running_total_matches_scan(self, temp_dirs, monkeypatch):
        from backend.config import settings

        monkeypatch.setattr(settings, "CACHE_MAX_SIZE_MB", 1)
        store, registry = _store()
        now = time.time()
        for i in range(8):
            _put(store, registry, SONG, i, 200_000, mtime=now - 100 + i)
            store.maybe_evict()
            assert store.total_bytes == _scan_total(store)
        _put(store, registry, SONG, 3, 50_000)  # overwrite an existing key
        assert store.total_bytes == _scan_total(store)
        store.purge_song(SONG)
        assert store.total_bytes == 0
        assert not store.song_dir(SONG).exists()


class TestLru:
    def test_lru_respects_access(self, temp_dirs, monkeypatch):
        """F11: a segment served recently survives over a newer never-served one."""
        from backend.config import settings

        monkeypatch.setattr(settings, "CACHE_MAX_SIZE_MB", 1)
        store, registry = _store()
        now = time.time()
        a = _put(store, registry, SONG, 0, 500_000, mtime=now - 3600)  # old download...
        b = _put(store, registry, OTHER, 0, 500_000, mtime=now - 60)   # newer download, never served
        store.touch(a)                                                 # ...but just served
        _put(store, registry, OTHER, 1, 200_000)                       # pushes the cache over 1 MB
        store.maybe_evict()
        assert a.exists()
        assert not b.exists()

    def test_touch_is_throttled(self, temp_dirs):
        store, registry = _store()
        path = _put(store, registry, SONG, 0, 10, mtime=1_000_000)
        store.touch(path)
        first = path.stat().st_mtime
        os.utime(path, (1_000_000, 1_000_000))
        store.touch(path)  # within 30 s: no utime
        assert first > 1_000_000
        assert path.stat().st_mtime == 1_000_000

    def test_eviction_updates_registry(self, temp_dirs, monkeypatch):
        from backend.config import settings

        monkeypatch.setattr(settings, "CACHE_MAX_SIZE_MB", 1)
        store, registry = _store()
        now = time.time()
        _put(store, registry, SONG, 0, 600_000, mtime=now - 100)
        _put(store, registry, SONG, 1, 600_000, mtime=now)
        store.maybe_evict()
        assert registry.get((SONG, 0)) == SegState.MISSING
        assert registry.get((SONG, 1)) == SegState.DONE

    def test_protected_and_in_flight_not_evicted(self, temp_dirs, monkeypatch):
        from backend.config import settings

        monkeypatch.setattr(settings, "CACHE_MAX_SIZE_MB", 1)
        monkeypatch.setattr(settings, "SEGMENT_BEHIND", 2)
        store, registry = _store()
        now = time.time()
        init = _put(store, registry, SONG, -1, 100_000, mtime=now - 500)
        behind = _put(store, registry, SONG, 1, 400_000, mtime=now - 400)   # before 5 - 2 = 3 → evictable
        kept = _put(store, registry, SONG, 3, 400_000, mtime=now - 300)     # within SEGMENT_BEHIND
        busy = _put(store, registry, OTHER, 0, 400_000, mtime=now - 200)
        registry.evicted((OTHER, 0))  # pretend it is being re-downloaded right now
        assert registry.claim((OTHER, 0))
        store.maybe_evict(protected=(SONG, 5))
        assert init.exists() and kept.exists() and busy.exists()
        assert not behind.exists()

    def test_layout_manifest_never_evicted(self, temp_dirs, monkeypatch):
        from backend.config import settings
        from backend.utils.layout import StreamInfo

        monkeypatch.setattr(settings, "CACHE_MAX_SIZE_MB", 1)
        store, registry = _store()
        store.write_layout_manifest(StreamInfo(song_id=SONG, title="", duration_ms=1, mime_type="audio/mp4",
                                               init_range=(0, -1)))
        _put(store, registry, SONG, 0, 1_200_000)
        store.maybe_evict()
        assert store.layout_path(SONG).exists()
        assert store.info()["file_count"] == 0

    def test_under_limit_is_noop(self, temp_dirs):
        store, registry = _store()
        path = _put(store, registry, SONG, 0, 100)
        assert store.maybe_evict() == 0
        assert path.exists()


class TestReconcile:
    def test_rebuilds_registry_and_total(self, temp_dirs):
        from backend.utils.layout import StreamInfo

        store, registry = _store()
        info = StreamInfo(song_id=SONG, title="", duration_ms=1, mime_type="audio/mp4", init_range=(0, -1))
        store.write_layout_manifest(info)
        store.write_segment(SONG, 0, b"a" * 10)
        store.record_segment(SONG, 0, 0, 9, 10, 5000, info.layout_id)
        (store.song_dir(SONG) / "0001.abcd.tmp").write_bytes(b"partial")

        fresh_store, fresh_registry = _store()
        counts = fresh_store.reconcile()
        assert fresh_registry.get((SONG, 0)) == SegState.DONE
        assert fresh_store.total_bytes == 10
        assert counts["orphans"] == 1
        assert not (store.song_dir(SONG) / "0001.abcd.tmp").exists()
