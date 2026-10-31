"""Unit tests for utils/mp4.py — box iteration, sidx parsing, fMP4 index.

Synthetic buffers plus one real header: fixtures/itag140_head.bin is the
first 1,012 bytes (ftyp + moov + sidx) of BAgTQhR8MLo itag 140 — media
metadata only, no URL, no cookies.
"""

import struct
from pathlib import Path

import pytest

from backend.utils.layout import SegmentInfo, StreamInfo, build_virtual_layout
from backend.utils.mp4 import NeedMoreData, iter_boxes, parse_fmp4_index, parse_sidx

FIXTURE = Path(__file__).parent / "fixtures" / "itag140_head.bin"
FIXTURE_FILESIZE = 4_172_237   # yt-dlp filesize for BAgTQhR8MLo itag 140
FIXTURE_DURATION_MS = 258_000  # yt-dlp duration (whole seconds)


def box(kind: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def sidx(refs, timescale=44100, version=0, first_offset=0, ref_type=0):
    """refs: [(size, duration)]."""
    body = struct.pack(">B3xII", version, 1, timescale)
    body += struct.pack(">II" if version == 0 else ">QQ", 0, first_offset)
    body += struct.pack(">HH", 0, len(refs))
    for size, duration in refs:
        body += struct.pack(">III", (ref_type << 31) | size, duration, 0x90000000)
    return box(b"sidx", body)


def fmp4_head(refs, moov_len=100, **kw):
    return box(b"ftyp", b"M4A " + b"\0" * 12) + box(b"moov", b"\0" * moov_len) + sidx(refs, **kw) + box(b"moof", b"\0" * 8)


class TestIterBoxes:
    def test_iter_boxes_basic(self):
        buf = box(b"ftyp", b"x" * 16) + box(b"moov", b"y" * 100)
        assert list(iter_boxes(buf)) == [("ftyp", 0, 24), ("moov", 24, 108)]

    def test_iter_boxes_largesize(self):
        buf = struct.pack(">I4sQ", 1, b"mdat", 16 + 4) + b"abcd" + box(b"free")
        assert list(iter_boxes(buf)) == [("mdat", 0, 20), ("free", 20, 8)]

    def test_iter_boxes_size_zero(self):
        buf = box(b"ftyp", b"x" * 8) + struct.pack(">I4s", 0, b"mdat") + b"z" * 50
        assert list(iter_boxes(buf)) == [("ftyp", 0, 16), ("mdat", 16, 58)]

    def test_iter_boxes_start_offset(self):
        buf = box(b"ftyp", b"x" * 8) + box(b"moov")
        assert list(iter_boxes(buf, 16)) == [("moov", 16, 8)]

    def test_iter_boxes_partial_header_stops(self):
        buf = box(b"ftyp", b"x" * 8) + b"\0\0\0"
        assert list(iter_boxes(buf)) == [("ftyp", 0, 16)]

    def test_iter_boxes_invalid_size(self):
        with pytest.raises(ValueError):
            list(iter_boxes(struct.pack(">I4s", 4, b"bad!")))


class TestParseSidx:
    def test_parse_sidx_v0(self):
        buf = b"\0" * 10 + sidx([(1000, 441000), (2000, 220500)], first_offset=7)
        assert parse_sidx(buf, 10) == (44100, 7, [(1000, 441000), (2000, 220500)])

    def test_parse_sidx_v1(self):
        buf = sidx([(1500, 48000)], timescale=48000, version=1, first_offset=2**33)
        assert parse_sidx(buf, 0) == (48000, 2**33, [(1500, 48000)])

    def test_hierarchical_sidx_rejected(self):
        with pytest.raises(ValueError, match="hierarchical"):
            parse_sidx(sidx([(1000, 100)], ref_type=1), 0)

    def test_not_a_sidx(self):
        with pytest.raises(ValueError):
            parse_sidx(box(b"moov", b"\0" * 40), 0)

    def test_truncated_sidx_needs_more(self):
        full = sidx([(1000, 100)] * 3)
        with pytest.raises(NeedMoreData) as e:
            parse_sidx(full[:-5], 0)
        assert e.value.required_len == len(full)


class TestParseFmp4Index:
    def test_synthetic_index(self):
        refs = [(1000, 441000), (2000, 441000), (500, 22050)]
        head = fmp4_head(refs)
        sidx_end = 24 + 108 + len(sidx(refs))
        idx = parse_fmp4_index(head)
        assert idx.timescale == 44100
        assert idx.init_end == sidx_end - 1
        assert idx.segments == [
            (sidx_end, sidx_end + 999, 10_000),
            (sidx_end + 1000, sidx_end + 2999, 10_000),
            (sidx_end + 3000, sidx_end + 3499, 500),
        ]
        assert idx.total_bytes == sidx_end + 3500
        assert idx.duration_ms == 20_500

    def test_first_offset_shifts_fragments(self):
        refs = [(1000, 44100)]
        head = fmp4_head(refs, first_offset=40)
        sidx_end = 24 + 108 + len(sidx(refs, first_offset=40))
        idx = parse_fmp4_index(head)
        assert idx.segments[0][0] == sidx_end + 40
        assert idx.init_end == sidx_end + 39

    def test_cumulative_rounding_sums_exactly(self):
        refs = [(100, 1)] * 3000  # 1/44100 s each
        idx = parse_fmp4_index(fmp4_head(refs))
        assert idx.duration_ms == 3000 * 1000 // 44100

    def test_need_more_data(self):
        refs = [(1000, 44100)] * 10
        head = fmp4_head(refs)
        sidx_end = 24 + 108 + len(sidx(refs))
        with pytest.raises(NeedMoreData) as e:
            parse_fmp4_index(head[:sidx_end - 20])  # sidx header visible, body cut
        assert e.value.required_len == sidx_end
        with pytest.raises(NeedMoreData) as e:
            parse_fmp4_index(head[:60])  # inside moov
        assert e.value.required_len == 24 + 108 + 8
        assert parse_fmp4_index(head[:sidx_end]).init_end == sidx_end - 1

    def test_no_sidx_before_fragment(self):
        head = box(b"ftyp", b"x" * 8) + box(b"moov", b"\0" * 20) + box(b"moof", b"\0" * 8)
        with pytest.raises(ValueError, match="no sidx"):
            parse_fmp4_index(head)

    def test_parse_fmp4_index_fixture(self):
        head = FIXTURE.read_bytes()
        idx = parse_fmp4_index(head)
        assert idx.init_end == len(head) - 1 > 0  # fixture ends exactly at the end of sidx
        assert idx.timescale == 44100
        assert len(idx.segments) == 26
        assert idx.segments[0][0] == idx.init_end + 1
        for (_, prev_end, _), (start, _, _) in zip(idx.segments, idx.segments[1:]):
            assert start == prev_end + 1
        assert idx.total_bytes == FIXTURE_FILESIZE
        assert abs(idx.duration_ms - FIXTURE_DURATION_MS) <= 1000

    def test_virtual_layout_equals_file(self):
        idx = parse_fmp4_index(FIXTURE.read_bytes())
        info = StreamInfo(
            song_id="BAgTQhR8MLo", title="t", duration_ms=idx.duration_ms, mime_type="audio/mp4",
            init_range=(0, idx.init_end),
            segments=[SegmentInfo(i, s, e, d, "u") for i, (s, e, d) in enumerate(idx.segments)],
        )
        layout = build_virtual_layout(info)
        assert all(virt_start == file_offset for virt_start, _, _, file_offset in layout)
        assert info.total_bytes == FIXTURE_FILESIZE
