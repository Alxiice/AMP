"""CacheStore — segment files on disk: paths, layout.json identity, size accounting,
LRU eviction and startup reconciliation.

LRU source is file mtime: written on download, bumped by touch() when a
segment is served (F11). A per-file size map keeps the running total exact,
so the check after each write is O(1) while under the limit.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.config import settings
from backend.database.models import Segment
from backend.database.session import session_scope
from backend.services.streaming.registry import SegmentRegistry
from backend.utils.layout import StreamInfo
from backend.utils.logger import get_logger

logger = get_logger("backend.services.streaming.cache")

LAYOUT_MANIFEST = "layout.json"
INIT_FILE = "init.bin"
TOUCH_INTERVAL_S = 30   # bump a served segment's mtime at most this often
EVICT_TO_FRACTION = 0.80


def atomic_replace(tmp: str, dest: Path, expected_size: int) -> None:
    """os.replace with Windows in mind: replacing a file another thread is
    replacing (or reading) raises PermissionError there. Retry briefly; if dest
    already holds expected_size bytes, a concurrent writer of the same range
    won and our identical copy is dropped."""
    for attempt in range(5):
        try:
            os.replace(tmp, dest)
            return
        except PermissionError:
            try:
                if dest.stat().st_size == expected_size:
                    os.unlink(tmp)
                    return
            except OSError:
                pass
            time.sleep(0.02 * (attempt + 1))
    os.replace(tmp, dest)


def parse_segment_name(name: str) -> Optional[int]:
    """'init.bin' → -1, '0012.bin' → 12, anything else → None."""
    if name == INIT_FILE:
        return -1
    stem, dot, ext = name.partition(".")
    if ext != "bin" or not stem.isdigit():
        return None
    return int(stem)


class CacheStore:
    def __init__(self, registry: SegmentRegistry) -> None:
        self._registry = registry
        self._lock = threading.Lock()
        self._sizes: Dict[Path, int] = {}       # segment file -> bytes (manifests excluded)
        self._total = 0
        self._touched: Dict[Path, float] = {}   # last touch() per file

    # --- Paths ---

    def song_dir(self, song_id: str) -> Path:
        return settings.segments_dir / song_id

    def segment_path(self, song_id: str, index: int) -> Path:
        if index == -1:
            return self.song_dir(song_id) / INIT_FILE
        return self.song_dir(song_id) / f"{index:04d}.bin"

    def layout_path(self, song_id: str) -> Path:
        return self.song_dir(song_id) / LAYOUT_MANIFEST

    # --- Size accounting ---

    @property
    def total_bytes(self) -> int:
        with self._lock:
            return self._total

    def _account(self, path: Path, size: int) -> None:
        with self._lock:
            self._total += size - self._sizes.get(path, 0)
            self._sizes[path] = size

    def _unaccount(self, path: Path) -> None:
        with self._lock:
            self._total -= self._sizes.pop(path, 0)
            self._touched.pop(path, None)

    def rescan(self) -> int:
        """Recompute sizes from disk (startup, or files written behind our back)."""
        sizes: Dict[Path, int] = {}
        root = settings.segments_dir
        if root.exists():
            for song_dir in root.iterdir():
                if not song_dir.is_dir():
                    continue
                for f in song_dir.iterdir():
                    if f.is_file() and parse_segment_name(f.name) is not None:
                        try:
                            sizes[f] = f.stat().st_size
                        except OSError:
                            pass
        with self._lock:
            self._sizes = sizes
            self._total = sum(sizes.values())
            return self._total

    # --- Writes ---

    def write_segment(self, song_id: str, index: int, data: bytes) -> Path:
        """Atomic write of in-memory bytes (P15: unique tmp + fsync + os.replace)."""
        final = self.segment_path(song_id, index)
        final.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=final.parent, prefix=f"{final.stem}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            atomic_replace(tmp, final, len(data))
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return final

    def record_segment(
        self, song_id: str, index: int, byte_start: int, byte_end: int,
        size_bytes: int, duration_ms: int, layout_id: Optional[str],
    ) -> None:
        """Account a file that is now on disk and record its DB row."""
        path = self.segment_path(song_id, index)
        self._account(path, size_bytes)
        try:
            with session_scope() as session:
                row = session.get(Segment, (song_id, index))
                if row is None:
                    row = Segment(song_id=song_id, index=index)
                    session.add(row)
                row.byte_start = byte_start
                row.byte_end = byte_end
                row.size_bytes = size_bytes
                row.duration_ms = duration_ms
                row.status = "downloaded"
                row.file_path = str(path)
                row.layout_id = layout_id
        except Exception as e:
            logger.error("Failed to record segment DB row %s seg %d: %s", song_id, index, e)

    def remove_segment(self, song_id: str, index: int) -> None:
        """Delete one segment file + DB row and tell the registry."""
        path = self.segment_path(song_id, index)
        path.unlink(missing_ok=True)
        self._unaccount(path)
        self._delete_row(song_id, index)
        self._registry.evicted((song_id, index))

    def _delete_row(self, song_id: str, index: int) -> None:
        try:
            with session_scope() as session:
                row = session.get(Segment, (song_id, index))
                if row:
                    session.delete(row)
        except Exception as e:
            logger.debug("Failed to delete segment row %s seg %d: %s", song_id, index, e)

    # --- LRU ---

    def touch(self, path: Path) -> None:
        """Mark a segment as used now (mtime), at most once per TOUCH_INTERVAL_S."""
        now = time.time()
        with self._lock:
            if now - self._touched.get(path, 0) < TOUCH_INTERVAL_S:
                return
            self._touched[path] = now
        try:
            os.utime(path)
        except OSError:
            pass

    def maybe_evict(self, protected: Optional[Tuple[str, int]] = None) -> int:
        """If over CACHE_MAX_SIZE_MB, evict least recently used segments to 80%.

        protected = (playing song_id, current segment index): its init.bin and
        every segment from index - SEGMENT_BEHIND on are kept. IN_FLIGHT
        segments and layout.json are never evicted. Returns bytes evicted.
        """
        max_bytes = settings.cache_max_bytes
        with self._lock:
            if self._total <= max_bytes:
                return 0
            candidates = list(self._sizes.items())
        target = int(max_bytes * EVICT_TO_FRACTION)
        logger.info("Cache over limit (%d > %d), evicting to %d", self.total_bytes, max_bytes, target)

        def mtime(path: Path) -> float:
            try:
                return path.stat().st_mtime
            except OSError:
                return 0.0

        evicted = 0
        for path, size in sorted(candidates, key=lambda c: mtime(c[0])):
            if self.total_bytes <= target:
                break
            song_id, index = path.parent.name, parse_segment_name(path.name)
            if index is None or self._is_protected(song_id, index, protected):
                continue
            self.remove_segment(song_id, index)
            evicted += size
            logger.debug("Evicted %s seg %d (%d bytes)", song_id, index, size)
        for song_id in {p.parent.name for p, _ in candidates}:
            self._remove_dir_if_empty(song_id)
        logger.info("Cache cleanup done: %d bytes evicted, %d remaining", evicted, self.total_bytes)
        return evicted

    def _is_protected(self, song_id: str, index: int, protected: Optional[Tuple[str, int]]) -> bool:
        if self._registry.is_in_flight((song_id, index)):
            return True
        if protected is None or song_id != protected[0]:
            return False
        return index == -1 or index >= protected[1] - settings.SEGMENT_BEHIND

    def _remove_dir_if_empty(self, song_id: str) -> None:
        """rmdir only if truly empty. layout.json stays even when every segment is
        evicted: the in-memory table still refers to it, and a directory without
        it would be purged as legacy at the next startup."""
        try:
            self.song_dir(song_id).rmdir()
        except OSError:
            pass

    # --- Cache identity (layout.json) ---

    def read_layout_id(self, song_id: str) -> Optional[str]:
        try:
            return json.loads(self.layout_path(song_id).read_text(encoding="utf-8")).get("layout_id")
        except (OSError, ValueError, AttributeError):
            return None

    def apply_layout(self, info: StreamInfo) -> bool:
        """Purge the song's cache if it was written under another layout, then
        record this one. Returns True if a purge happened."""
        song_id = info.song_id
        on_disk = self.read_layout_id(song_id)
        if on_disk == info.layout_id:
            return False
        song_dir = self.song_dir(song_id)
        purged = song_dir.exists() and any(song_dir.iterdir())
        if purged:
            logger.info(
                "Layout changed for %s (%s -> %s, %s): purging cached segments",
                song_id, on_disk or "none", info.layout_id, info.method,
            )
            self.purge_song(song_id)
        self.write_layout_manifest(info)
        return purged

    def write_layout_manifest(self, info: StreamInfo) -> None:
        manifest = {
            "layout_id": info.layout_id,
            "method": info.method,
            "itag": info.itag,
            "mime_type": info.mime_type,
            "total_bytes": info.total_bytes,
            "duration_ms": info.duration_ms,
            "init_range": list(info.init_range),
            "segments": [[s.byte_start, s.byte_end, s.duration_ms] for s in info.segments],
        }
        path = self.layout_path(info.song_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="layout.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:  # P15
            json.dump(manifest, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def purge_song(self, song_id: str) -> None:
        """Delete a song's files, DB rows, accounting and registry entries."""
        song_dir = self.song_dir(song_id)
        shutil.rmtree(song_dir, ignore_errors=True)
        with self._lock:
            for path in [p for p in self._sizes if p.parent == song_dir]:
                self._total -= self._sizes.pop(path)
                self._touched.pop(path, None)
        try:
            with session_scope() as session:
                session.query(Segment).filter(Segment.song_id == song_id).delete()
        except Exception as e:
            logger.error("Failed to delete segment rows for %s: %s", song_id, e)
        self._registry.forget(song_id)

    # --- Startup reconciliation ---

    def reconcile(self) -> Dict[str, int]:
        """Heal crash damage and rebuild the registry + size map from disk (§6.6)."""
        logger.info("Reconciling segment cache...")
        counts = {"orphans": 0, "missing": 0, "mismatches": 0, "legacy_dirs": 0}
        root = settings.segments_dir
        if not root.exists():
            return counts

        rows: Dict[Tuple[str, int], Tuple[int, Optional[str]]] = {}
        try:
            with session_scope() as session:
                for seg in session.query(Segment).all():
                    rows[(seg.song_id, seg.index)] = (seg.size_bytes, seg.layout_id)
        except Exception as e:
            logger.error("Failed to read segment DB rows: %s", e)
            return counts

        on_disk: set = set()
        for song_dir in list(root.iterdir()):
            if not song_dir.is_dir():
                continue
            song_id = song_dir.name
            layout_id = self.read_layout_id(song_id)
            if layout_id is None:
                # No layout.json: written before Phase 2 (proportional layout) or
                # never completed — its segments can't be trusted
                self.purge_song(song_id)
                counts["legacy_dirs"] += 1
                continue
            for f in song_dir.iterdir():
                if not f.is_file() or f.name == LAYOUT_MANIFEST:
                    continue
                index = parse_segment_name(f.name)
                if index is None:  # *.tmp from a crashed download, or junk
                    f.unlink(missing_ok=True)
                    counts["orphans"] += 1
                    continue
                key = (song_id, index)
                row = rows.get(key)
                if row is None:
                    f.unlink(missing_ok=True)
                    counts["orphans"] += 1
                    continue
                try:
                    size = f.stat().st_size
                except OSError:
                    continue
                if size != row[0] or row[1] != layout_id:
                    f.unlink(missing_ok=True)
                    self._delete_row(song_id, index)
                    counts["mismatches"] += 1
                    continue
                on_disk.add(key)
                self._registry.mark_done(key)

        for key in rows:
            if key not in on_disk and not self.segment_path(*key).exists():
                self._delete_row(*key)
                counts["missing"] += 1

        self.rescan()
        logger.info(
            "Reconciliation done: %d orphans, %d missing, %d mismatches, %d song dirs without %s removed",
            counts["orphans"], counts["missing"], counts["mismatches"], counts["legacy_dirs"], LAYOUT_MANIFEST,
        )
        return counts

    # --- Stats ---

    def info(self) -> Dict[str, Any]:
        """Cache statistics: total size, file count, per-song breakdown."""
        with self._lock:
            items = list(self._sizes.items())
        per_song: Dict[str, List[int]] = {}
        for path, size in items:
            per_song.setdefault(path.parent.name, []).append(size)
        songs = [
            {"song_id": song_id, "size_bytes": sum(sizes), "file_count": len(sizes)}
            for song_id, sizes in sorted(per_song.items())
        ]
        total = sum(size for _, size in items)
        max_bytes = settings.cache_max_bytes
        return {
            "total_bytes": total,
            "total_mb": round(total / (1024 * 1024), 2),
            "max_mb": settings.CACHE_MAX_SIZE_MB,
            "usage_pct": round(total / max_bytes * 100, 1) if max_bytes > 0 else 0,
            "file_count": len(items),
            "song_count": len(songs),
            "songs": songs,
        }
