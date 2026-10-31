"""Integration tests — network + cookies required.

Run with: pytest -m integration

Pinned songs:
  - dQw4w9WgXcQ (Rick Astley — Never Gonna Give You Up)
  - LTDxBgP0lqA (The Weeknd — Blinding Lights)

If either breaks (removed/region-blocked), update the IDs — accepted per scope.

Prerequisites:
  - Cookies saved to .amp/cache/ytm_session.json (via auth flow)
  - Node.js 18+ installed (yt-dlp JS challenges)
  - Network access to YouTube
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

PINNED_SONGS = ["dQw4w9WgXcQ", "LTDxBgP0lqA"]


@pytest.fixture()
def streaming_service(temp_dirs):
    """StreamingService with real network access."""
    from backend.services.streaming import StreamingService
    svc = StreamingService()
    svc.start()
    yield svc
    svc.stop()


class TestManifestFetchAndParse:
    """End-to-end: yt-dlp → manifest URL → MPD fetch → parse."""

    @pytest.mark.parametrize("song_id", PINNED_SONGS)
    def test_stream_info(self, streaming_service, song_id):
        info = streaming_service._get_stream_info(song_id)
        assert info is not None, f"No stream info for {song_id}"
        assert len(info.segments) > 0, f"No segments for {song_id}"
        assert info.total_bytes > 0
        assert info.duration_ms > 0
        assert info.mime_type in ("audio/mp4", "audio/webm")


class TestSegmentDownload:
    """Download init + first 3 segments, verify sizes."""

    @pytest.mark.parametrize("song_id", PINNED_SONGS[:1])  # Just first song for speed
    def test_download_first_segments(self, streaming_service, song_id, temp_dirs):
        info = streaming_service._get_stream_info(song_id)
        assert info is not None

        # Download init (DASH only; progressive streams have none)
        assert streaming_service.ensure_segment(song_id, -1).exists()
        if info.has_init:
            init_path = streaming_service._cache.segment_path(song_id, -1)
            assert init_path.exists()
            init_size = init_path.stat().st_size
            expected_init = info.init_range[1] - info.init_range[0] + 1
            assert init_size == expected_init, f"Init size mismatch: {init_size} != {expected_init}"

        # Download first 3 segments
        for i in range(min(3, len(info.segments))):
            assert streaming_service.ensure_segment(song_id, i).exists()
            path = streaming_service._cache.segment_path(song_id, i)
            assert path.exists()
            seg = info.segments[i]
            expected = seg.byte_end - seg.byte_start + 1
            actual = path.stat().st_size
            assert actual == expected, f"Segment {i} size mismatch: {actual} != {expected}"


class TestAudioEndpoint:
    """Full audio endpoint: Range requests return correct bytes."""

    @pytest.mark.parametrize("song_id", PINNED_SONGS[:1])
    def test_range_request_206(self, streaming_service, song_id):
        info = streaming_service._get_stream_info(song_id)
        assert info is not None

        status, headers, body = streaming_service.serve_audio_range(
            song_id, "bytes=0-1023"
        )
        assert status == 206
        assert "Content-Range" in headers
        assert headers["Content-Range"].startswith("bytes 0-1023/")
        assert headers["Content-Length"] == "1024"

        # Consume the generator
        data = b"".join(body)
        assert len(data) == 1024

    @pytest.mark.parametrize("song_id", PINNED_SONGS[:1])
    def test_open_ended_range(self, streaming_service, song_id):
        info = streaming_service._get_stream_info(song_id)
        assert info is not None

        # bytes=0- should return from 0 to end
        status, headers, body = streaming_service.serve_audio_range(
            song_id, "bytes=0-"
        )
        assert status == 206
        assert headers["Content-Length"] == str(info.total_bytes)

    @pytest.mark.parametrize("song_id", PINNED_SONGS[:1])
    def test_unsatisfiable_range(self, streaming_service, song_id):
        info = streaming_service._get_stream_info(song_id)
        assert info is not None

        status, headers, body = streaming_service.serve_audio_range(
            song_id, f"bytes={info.total_bytes}-{info.total_bytes + 100}"
        )
        assert status == 416
        assert "Content-Range" in headers
        assert f"bytes */{info.total_bytes}" == headers["Content-Range"]

    @pytest.mark.parametrize("song_id", PINNED_SONGS[:1])
    def test_no_range_header(self, streaming_service, song_id):
        info = streaming_service._get_stream_info(song_id)
        assert info is not None

        status, headers, body = streaming_service.serve_audio_range(song_id, None)
        assert status == 200
        assert headers["Content-Length"] == str(info.total_bytes)
        assert headers["Accept-Ranges"] == "bytes"


class TestCacheEviction:
    """Cache eviction with a temp cache dir."""

    def test_eviction_and_reconciliation(self, temp_dirs):
        from backend.config import settings
        from backend.services.streaming import StreamingService

        # Create fake segment files exceeding the limit
        for i in range(5):
            song_dir = settings.segments_dir / f"song{i:07d}AAA"
            song_dir.mkdir(parents=True)
            (song_dir / "0000.bin").write_bytes(b"\x00" * 300_000)  # 300KB each = 1.5MB

        svc = StreamingService()
        svc.cleanup_cache()

        total = sum(
            f.stat().st_size
            for song_dir in settings.segments_dir.iterdir()
            if song_dir.is_dir()
            for f in song_dir.iterdir()
            if f.is_file()
        )
        # Should be <= 80% of 1MB
        assert total <= 800_000

        # Reconciliation should not error
        svc.reconcile_cache()
