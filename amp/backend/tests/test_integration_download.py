"""Integration test — manual download chunks validation.

Run with:
    pytest backend/tests/test_integration_download.py -m integration -v -s

Or with a custom song ID:
    AMP_TEST_SONG_ID=Tmz3mpOq8aE pytest backend/tests/test_integration_download.py -m integration -v -s

Default song: BAgTQhR8MLo (user-reported failing video)

Prerequisites:
    - Node.js 18+ installed (yt-dlp JS challenges)
    - Network access to YouTube
    - Cookies optional (saved to .amp/cache/ytm_session.json via auth flow)

What it validates:
    1. yt-dlp can extract a stream URL for the song
    2. Stream info is built (segments, total_bytes, duration)
    3. All chunks (init + media segments) download successfully
    4. Downloaded file sizes match expected byte ranges
    5. Total downloaded bytes match StreamInfo.total_bytes
    6. Audio range serving returns correct bytes
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

# Default song — override with AMP_TEST_SONG_ID env var
DEFAULT_SONG_ID = "BAgTQhR8MLo"
SONG_ID = os.environ.get("AMP_TEST_SONG_ID", DEFAULT_SONG_ID)

# Safety limits
MAX_DOWNLOAD_SECONDS = 300  # 5 minutes max for full download
PROGRESS_INTERVAL = 10      # Print progress every N segments


@pytest.fixture()
def streaming_service(temp_dirs, monkeypatch):
    """StreamingService with real network access and temp cache dirs.

    Overrides CACHE_MAX_SIZE_MB to 0 (unlimited) so LRU eviction doesn't
    delete segments during the full download test.
    """
    from backend.config import settings
    monkeypatch.setattr(settings, "CACHE_MAX_SIZE_MB", 10000)  # 10 GB — effectively unlimited for integration tests

    from backend.services.streaming import StreamingService
    svc = StreamingService()
    svc.start()
    yield svc
    svc.stop()


class TestDownloadChunks:
    """Full chunk download validation for a single song."""

    def test_download_chunks(self, streaming_service, temp_dirs):
        """Download ALL chunks for the test song and verify completeness.

        Steps:
            1. Extract stream URL via yt-dlp (multi-strategy)
            2. Build stream info (DASH manifest parse or progressive fallback)
            3. Download init segment + all media segments
            4. Verify every segment file exists with correct size
            5. Verify total bytes match StreamInfo.total_bytes
            6. Verify audio range serving returns correct bytes
        """
        song_id = SONG_ID
        print(f"\n{'='*60}")
        print(f"  Integration Test: Download Chunks")
        print(f"  Song ID: {song_id}")
        print(f"  URL: https://music.youtube.com/watch?v={song_id}")
        print(f"{'='*60}\n")

        # --- Step 1: Get stream info (triggers yt-dlp extraction + manifest parse) ---
        print(f"[1/6] Fetching stream info for {song_id}...")
        t0 = time.time()
        info = streaming_service._get_stream_info(song_id)
        t1 = time.time()

        assert info is not None, (
            f"FAILED: Could not get stream info for {song_id}.\n"
            f"  This means yt-dlp extraction failed after all strategies.\n"
            f"  Check the logs above for 'Diagnostic' output showing available formats.\n"
            f"  The video may be region-locked, age-restricted, or unavailable."
        )

        print(f"  OK — stream info built in {t1-t0:.1f}s")
        print(f"    Type:       {'DASH' if info.is_dash else 'Progressive'}")
        print(f"    Segments:   {len(info.segments)}")
        print(f"    Duration:   {info.duration_ms / 1000:.1f}s")
        print(f"    Total:      {info.total_bytes:,} bytes ({info.total_bytes / 1024 / 1024:.2f} MB)")
        print(f"    MIME:       {info.mime_type}")
        print(f"    Init range: bytes {info.init_range[0]}-{info.init_range[1]}")
        print(f"    Base URL:   {info.base_url[:80]}...")

        # --- Step 2: Verify segment structure ---
        print(f"\n[2/6] Validating segment structure...")
        assert len(info.segments) > 0, "No segments in stream info"
        assert info.total_bytes > 0, "total_bytes is 0"

        # Verify total_bytes matches init + sum of segment sizes
        expected_total = (info.init_range[1] - info.init_range[0] + 1) + sum(
            s.byte_end - s.byte_start + 1 for s in info.segments
        )
        assert info.total_bytes == expected_total, (
            f"total_bytes mismatch: {info.total_bytes} != {expected_total}"
        )
        print(f"  OK — {len(info.segments)} segments, total_bytes consistent")

        # --- Step 3: Download init segment (DASH only; progressive streams have none) ---
        if info.has_init:
            print(f"\n[3/6] Downloading init segment...")
            t0 = time.time()
            ok = streaming_service.ensure_segment(song_id, -1).exists()
            t1 = time.time()
            assert ok, "FAILED: init segment download returned False"

            init_path = streaming_service._cache.segment_path(song_id, -1)
            assert init_path.exists(), f"FAILED: init segment file not found at {init_path}"
            init_size = init_path.stat().st_size
            expected_init = info.init_range[1] - info.init_range[0] + 1
            assert init_size == expected_init, (
                f"Init size mismatch: {init_size} != {expected_init}"
            )
            print(f"  OK — init segment downloaded ({init_size:,} bytes) in {t1-t0:.1f}s")
        else:
            init_size = 0
            print(f"\n[3/6] No init segment (progressive stream) — skipped")

        # --- Step 4: Download all media segments ---
        total_segments = len(info.segments)
        print(f"\n[4/6] Downloading {total_segments} media segments...")
        print(f"  (max {MAX_DOWNLOAD_SECONDS}s, progress every {PROGRESS_INTERVAL} segments)")

        t0 = time.time()
        failed: list[int] = []
        downloaded_bytes = init_size

        for i in range(total_segments):
            seg_ok = streaming_service.ensure_segment(song_id, i).exists()
            if not seg_ok:
                failed.append(i)
                print(f"  FAIL: segment {i} download failed")
                continue

            path = streaming_service._cache.segment_path(song_id, i)
            if path.exists():
                seg_size = path.stat().st_size
                downloaded_bytes += seg_size
                expected_seg = info.segments[i].byte_end - info.segments[i].byte_start + 1
                if seg_size != expected_seg:
                    print(f"  WARN: segment {i} size mismatch: {seg_size} != {expected_seg}")

            if (i + 1) % PROGRESS_INTERVAL == 0 or i == total_segments - 1:
                elapsed = time.time() - t0
                pct = (i + 1) / total_segments * 100
                print(f"  [{i+1}/{total_segments}] {pct:.0f}% — {elapsed:.1f}s elapsed")

            # Safety: don't run forever
            if time.time() - t0 > MAX_DOWNLOAD_SECONDS:
                pytest.fail(
                    f"Download timed out after {MAX_DOWNLOAD_SECONDS}s "
                    f"at segment {i+1}/{total_segments}"
                )

        t1 = time.time()
        download_time = t1 - t0

        # --- Step 5: Verify all segments ---
        print(f"\n[5/6] Verifying all downloaded segments...")
        all_ok = True
        total_expected = info.init_range[1] - info.init_range[0] + 1
        total_actual = 0
        missing: list[int] = []
        size_mismatches: list[tuple[int, int, int]] = []

        for i in range(total_segments):
            path = streaming_service._cache.segment_path(song_id, i)
            seg = info.segments[i]
            expected = seg.byte_end - seg.byte_start + 1
            total_expected += expected

            if not path.exists():
                missing.append(i)
                all_ok = False
                continue

            actual = path.stat().st_size
            total_actual += actual
            if actual != expected:
                size_mismatches.append((i, actual, expected))
                all_ok = False

        # Also check init
        init_path = streaming_service._cache.segment_path(song_id, -1)
        if init_path.exists():
            total_actual += init_path.stat().st_size
        elif info.has_init:
            all_ok = False
            missing.append(-1)

        print(f"  Segments expected: {total_segments} (+ init)")
        print(f"  Segments on disk:  {total_segments - len([m for m in missing if m >= 0])} (+ init)")
        print(f"  Missing:           {len(missing)} {missing[:10]}{'...' if len(missing) > 10 else ''}")
        print(f"  Size mismatches:   {len(size_mismatches)} {size_mismatches[:5]}")
        print(f"  Total expected:    {total_expected:,} bytes")
        print(f"  Total actual:      {total_actual:,} bytes")
        print(f"  Download time:     {download_time:.1f}s")
        print(f"  Avg speed:         {total_actual / download_time / 1024:.1f} KB/s" if download_time > 0 else "")

        if failed:
            print(f"  Failed downloads:  {failed[:10]}{'...' if len(failed) > 10 else ''}")

        assert all_ok, (
            f"FAILED: Segment verification failed.\n"
            f"  Missing segments: {missing[:20]}\n"
            f"  Size mismatches: {size_mismatches[:10]}\n"
            f"  Failed downloads: {failed[:20]}"
        )
        assert total_actual == total_expected, (
            f"Total bytes mismatch: {total_actual:,} != {total_expected:,} "
            f"(diff: {total_actual - total_expected:+,})"
        )
        assert total_actual == info.total_bytes, (
            f"Downloaded bytes {total_actual:,} != StreamInfo.total_bytes {info.total_bytes:,}"
        )
        print(f"  OK — all {total_segments} segments verified, total bytes match")

        # --- Step 6: Verify audio range serving ---
        print(f"\n[6/6] Verifying audio range serving...")

        # Test a small range at the start
        status, headers, body = streaming_service.serve_audio_range(song_id, "bytes=0-1023")
        assert status == 206, f"Expected 206 for range request, got {status}"
        assert "Content-Range" in headers, "Missing Content-Range header"
        assert headers["Content-Range"].startswith("bytes 0-1023/"), f"Bad Content-Range: {headers.get('Content-Range')}"
        assert headers["Content-Length"] == "1024", f"Bad Content-Length: {headers.get('Content-Length')}"

        data = b"".join(body)
        assert len(data) == 1024, f"Range body size mismatch: {len(data)} != 1024"
        print(f"  OK — range bytes=0-1023 returns 206 with 1024 bytes")

        # Test a range in the middle
        mid = info.total_bytes // 2
        mid_end = min(mid + 4095, info.total_bytes - 1)
        status, headers, body = streaming_service.serve_audio_range(song_id, f"bytes={mid}-{mid_end}")
        assert status == 206, f"Expected 206 for mid-range, got {status}"
        data = b"".join(body)
        expected_len = mid_end - mid + 1
        assert len(data) == expected_len, f"Mid-range body size: {len(data)} != {expected_len}"
        print(f"  OK — range bytes={mid}-{mid_end} returns 206 with {expected_len} bytes")

        # Test full file (no range header)
        status, headers, body = streaming_service.serve_audio_range(song_id, None)
        assert status == 200, f"Expected 200 for no-range, got {status}"
        assert headers["Content-Length"] == str(info.total_bytes), (
            f"Full Content-Length: {headers.get('Content-Length')} != {info.total_bytes}"
        )
        # Consume in chunks to avoid loading entire file into memory at once
        total_served = 0
        for chunk in body:
            total_served += len(chunk)
        assert total_served == info.total_bytes, (
            f"Full audio served {total_served:,} bytes != {info.total_bytes:,}"
        )
        print(f"  OK — full audio (no range) returns 200 with {total_served:,} bytes")

        # --- Summary ---
        print(f"\n{'='*60}")
        print(f"  PASSED: All chunks downloaded and verified")
        print(f"  Song:       {song_id}")
        print(f"  Segments:   {total_segments} + init")
        print(f"  Total:      {total_actual:,} bytes ({total_actual / 1024 / 1024:.2f} MB)")
        print(f"  Time:       {download_time:.1f}s")
        print(f"  Speed:      {total_actual / download_time / 1024:.1f} KB/s" if download_time > 0 else "")
        print(f"{'='*60}\n")

    def test_download_chunks_quick(self, streaming_service, temp_dirs):
        """Quick variant: download only init + first 5 segments.

        Faster smoke test — validates extraction + manifest + partial download.
        """
        song_id = SONG_ID
        print(f"\n{'='*60}")
        print(f"  Quick Test: Download first 5 chunks for {song_id}")
        print(f"{'='*60}\n")

        info = streaming_service._get_stream_info(song_id)
        assert info is not None, f"Could not get stream info for {song_id}"
        print(f"  Stream info: {len(info.segments)} segments, {info.total_bytes:,} bytes total")

        # Download init + first 5
        targets = ([-1] if info.has_init else []) + list(range(min(5, len(info.segments))))
        for idx in targets:
            ok = streaming_service.ensure_segment(song_id, idx).exists()
            assert ok, f"Failed to download segment {idx}"
            path = streaming_service._cache.segment_path(song_id, idx)
            assert path.exists(), f"Segment {idx} file not found"
            size = path.stat().st_size
            if idx == -1:
                expected = info.init_range[1] - info.init_range[0] + 1
            else:
                expected = info.segments[idx].byte_end - info.segments[idx].byte_start + 1
            assert size == expected, f"Segment {idx} size {size} != {expected}"
            print(f"  OK — segment {idx}: {size:,} bytes")

        print(f"\n  PASSED: {len(targets)} chunks verified\n")


class TestConcatEqualsCdnFile:
    """Phase 2: the exact (sidx) segment table reassembles the CDN file byte for byte."""

    def test_concat_equals_cdn_file(self, streaming_service, temp_dirs):
        import hashlib

        import requests

        song_id = SONG_ID
        info = streaming_service._get_stream_info(song_id)
        assert info is not None, f"Could not get stream info for {song_id}"
        assert info.is_dash, f"Expected an exact sidx table for {song_id}, got {info.method}"
        assert abs(sum(s.duration_ms for s in info.segments) - info.duration_ms) <= 1000

        local = hashlib.sha256()
        for idx in [-1] + list(range(len(info.segments))):
            assert streaming_service.ensure_segment(song_id, idx).exists(), f"segment {idx} failed"
            local.update(streaming_service._cache.segment_path(song_id, idx).read_bytes())

        # One request for the whole file (googlevideo wants a Range for large reads)
        resp = requests.get(
            info.base_url,
            headers={**streaming_service._auth.get_cdn_headers(), "Range": f"bytes=0-{info.total_bytes - 1}"},
            timeout=60,
        )
        assert resp.status_code in (200, 206), f"CDN returned {resp.status_code}"
        assert len(resp.content) == info.total_bytes
        remote = hashlib.sha256(resp.content)
        print(f"\n  {song_id}: {len(info.segments)} sidx segments + init, {info.total_bytes:,} B, "
              f"sha256 {local.hexdigest()[:16]}")
        assert local.hexdigest() == remote.hexdigest()
