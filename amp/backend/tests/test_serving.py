"""Unit tests for services/streaming/serving.py — Range parsing, no short bodies (F7)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from backend.services.streaming.serving import SegmentUnavailable, parse_range, serve_audio_range
from backend.utils.layout import SegmentInfo, StreamInfo

SONG = "dQw4w9WgXcQ"


class FakeSource:
    """init 0-9 + 3 segments of 10 bytes; ensure_segment writes files on demand."""

    def __init__(self, root: Path, fail=(), vanish_once=(), info=True, code=None):
        self.root, self.fail, self.vanish_once, self.code = root, set(fail), set(vanish_once), code
        self.calls = []
        self.info = StreamInfo(
            song_id=SONG, title="", duration_ms=15_000, mime_type="audio/mp4", init_range=(0, 9),
            segments=[SegmentInfo(i, 10 + i * 10, 19 + i * 10, 5000, "u") for i in range(3)],
        ) if info else None

    def get_stream_info(self, song_id):
        return self.info

    def stream_error_code(self, song_id):
        return self.code

    def ensure_segment(self, song_id, index, timeout=None):
        self.calls.append(index)
        if index in self.fail:
            raise SegmentUnavailable(song_id, index, "boom")
        path = self.root / f"{index}.bin"
        if index in self.vanish_once:
            self.vanish_once.discard(index)
            return path  # never written: open() fails once
        path.write_bytes(bytes([65 + index + 1]) * 10)  # init 'A', seg0 'B', …
        return path


def _body(result):
    status, headers, body = result
    return status, headers, b"".join(body)


class TestParseRange:
    @pytest.mark.parametrize("header, expected", [
        (None, (0, 39)), ("bytes=0-9", (0, 9)), ("bytes=5-", (5, 39)), ("bytes=-5", (35, 39)),
        ("bytes=30-100", (30, 39)), ("bytes=40-", None), ("bytes=-0", None), ("bytes=-", None),
        ("junk", None), ("bytes=9-3", None),
    ])
    def test_parse(self, header, expected):
        assert parse_range(header, 40) == expected


class TestServe:
    def test_full_file(self, tmp_path):
        status, headers, body = _body(serve_audio_range(FakeSource(tmp_path), SONG))
        assert status == 200
        assert headers["Content-Length"] == "40"
        assert body == b"A" * 10 + b"B" * 10 + b"C" * 10 + b"D" * 10

    def test_range_spanning_segments(self, tmp_path):
        status, headers, body = _body(serve_audio_range(FakeSource(tmp_path), SONG, "bytes=15-24"))
        assert status == 206
        assert headers["Content-Range"] == "bytes 15-24/40"
        assert body == b"B" * 5 + b"C" * 5

    def test_unsatisfiable(self, tmp_path):
        status, headers, body = serve_audio_range(FakeSource(tmp_path), SONG, "bytes=40-")
        assert status == 416
        assert headers["Content-Range"] == "bytes */40"

    def test_range_first_segment_failure_returns_json_error(self, tmp_path):
        status, headers, body = serve_audio_range(FakeSource(tmp_path, fail={0}), SONG, "bytes=10-30")
        assert status == 502
        assert body["detail"]["code"] == "segment_unavailable"
        assert "Content-Range" not in headers and "Content-Length" not in headers

    def test_range_mid_stream_failure_raises(self, tmp_path):
        status, headers, body = serve_audio_range(FakeSource(tmp_path, fail={1}), SONG, "bytes=10-39")
        assert status == 206  # the first segment was available
        assert next(body) == b"B" * 10
        with pytest.raises(SegmentUnavailable):
            next(body)  # never a silently short body

    def test_vanished_file_is_refetched_once(self, tmp_path):
        source = FakeSource(tmp_path, vanish_once={1})
        status, _, body = _body(serve_audio_range(source, SONG, "bytes=10-29"))
        assert body == b"B" * 10 + b"C" * 10
        assert source.calls.count(1) == 2

    @pytest.mark.parametrize("code, status", [
        ("unavailable", 404), ("auth_required", 401), ("node_missing", 503), (None, 502),
    ])
    def test_no_stream_info_maps_extraction_code(self, tmp_path, code, status):
        result = serve_audio_range(FakeSource(tmp_path, info=False, code=code), SONG)
        assert result[0] == status
        assert result[2]["detail"]["code"] == (code or "extract_failed")


class TestAudioEndpoint:
    def test_first_segment_failure_is_json_502(self, client_no_auth, tmp_path):
        from backend.services.streaming import get_streaming_service

        svc = get_streaming_service()
        source = FakeSource(tmp_path, fail={-1})
        with patch.object(svc, "get_stream_info", source.get_stream_info), \
             patch.object(svc, "ensure_segment", source.ensure_segment):
            resp = client_no_auth.get(f"/api/stream/{SONG}/audio", headers={"Range": "bytes=0-"})
        assert resp.status_code == 502
        assert resp.json()["detail"]["code"] == "segment_unavailable"
        assert "content-range" not in resp.headers

    def test_mid_stream_failure_aborts_response(self, client_no_auth, tmp_path):
        from backend.services.streaming import get_streaming_service

        svc = get_streaming_service()
        source = FakeSource(tmp_path, fail={2})
        with patch.object(svc, "get_stream_info", source.get_stream_info), \
             patch.object(svc, "ensure_segment", source.ensure_segment):
            with pytest.raises(SegmentUnavailable):
                client_no_auth.get(f"/api/stream/{SONG}/audio", headers={"Range": "bytes=0-"})

    def test_416_keeps_content_range(self, client_no_auth, tmp_path):
        from backend.services.streaming import get_streaming_service

        svc = get_streaming_service()
        source = FakeSource(tmp_path)
        with patch.object(svc, "get_stream_info", source.get_stream_info):
            resp = client_no_auth.get(f"/api/stream/{SONG}/audio", headers={"Range": "bytes=99-"})
        assert resp.status_code == 416
        assert resp.headers["content-range"] == "bytes */40"
