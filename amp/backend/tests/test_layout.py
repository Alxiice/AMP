"""Unit tests for utils/layout.py — segment table types, byte-range math, range mapping.

Fully mocked, no network.
"""

import pytest

from backend.utils.layout import (
    StreamInfo,
    SegmentInfo,
    build_virtual_layout,
    compute_layout_id,
    map_range_to_segments,
    position_ms_to_segment_index,
)

URL = "https://cdn.example.com/videoplayback?expire=123"


def _sample_info(**kw):
    """init 0-623 + 5 segments of 50,000 bytes / 42 s each (210 s total)."""
    segments = [
        SegmentInfo(index=i, byte_start=624 + i * 50_000, byte_end=624 + (i + 1) * 50_000 - 1,
                    duration_ms=42_000, url=URL)
        for i in range(5)
    ]
    fields = dict(song_id="dQw4w9WgXcQ", title="t", duration_ms=210_000, mime_type="audio/mp4",
                  init_range=(0, 623), segments=segments, base_url=URL, itag="140")
    fields.update(kw)
    return StreamInfo(**fields)


class TestStreamInfo:
    def test_total_bytes(self):
        assert _sample_info().total_bytes == 250_624

    def test_no_init(self):
        info = _sample_info(init_range=(0, -1))
        assert not info.has_init
        assert info.init_size == 0

    def test_layout_id_stable(self):
        assert _sample_info().layout_id == _sample_info().layout_id
        assert len(_sample_info().layout_id) == 16

    def test_layout_id_changes_with_identity(self):
        base = _sample_info().layout_id
        assert _sample_info(itag="251").layout_id != base
        assert _sample_info(is_dash=False).layout_id != base
        assert _sample_info(segments=_sample_info().segments[:4]).layout_id != base

    def test_compute_layout_id(self):
        info = _sample_info()
        assert info.layout_id == compute_layout_id("140", 250_624, 5, "sidx")


# ---------------------------------------------------------------------------
# Virtual layout + range mapping
# ---------------------------------------------------------------------------


class TestVirtualLayout:
    @pytest.fixture()
    def stream_info(self):
        return _sample_info()

    def test_layout_entry_count(self, stream_info):
        layout = build_virtual_layout(stream_info)
        # 1 init + 5 segments = 6 entries
        assert len(layout) == 6

    def test_layout_init_first(self, stream_info):
        layout = build_virtual_layout(stream_info)
        # First entry: init segment
        virt_start, virt_end, seg_index, file_offset = layout[0]
        assert seg_index == -1
        assert virt_start == 0
        assert virt_end == 623  # init is 624 bytes (0-623)

    def test_layout_contiguous(self, stream_info):
        layout = build_virtual_layout(stream_info)
        for i in range(1, len(layout)):
            prev_end = layout[i - 1][1]
            curr_start = layout[i][0]
            assert curr_start == prev_end + 1, f"Gap at layout[{i}]"

    def test_layout_total(self, stream_info):
        layout = build_virtual_layout(stream_info)
        last_end = layout[-1][1]
        assert last_end == stream_info.total_bytes - 1


class TestRangeMapping:
    @pytest.fixture()
    def stream_info(self):
        return _sample_info()

    @pytest.fixture()
    def layout(self, stream_info):
        return build_virtual_layout(stream_info)

    def test_single_segment_range(self, layout):
        # Range entirely within init segment (0-623)
        reads = map_range_to_segments(layout, 100, 200)
        assert len(reads) == 1
        virt_start, virt_end, seg_index, file_offset, read_start, read_end = reads[0]
        assert seg_index == -1
        assert read_start == 100
        assert read_end == 200

    def test_spanning_two_segments(self, layout):
        # Range spanning init end + segment 0 start
        reads = map_range_to_segments(layout, 600, 700)
        assert len(reads) == 2
        # First read: init segment, bytes 600-623
        assert reads[0][2] == -1  # init
        assert reads[0][4] == 600  # read_start
        assert reads[0][5] == 623  # read_end
        # Second read: segment 0, bytes 0-76 (virtual 624-700)
        assert reads[1][2] == 0  # segment 0
        assert reads[1][4] == 0
        assert reads[1][5] == 76

    def test_full_range(self, layout, stream_info):
        reads = map_range_to_segments(layout, 0, stream_info.total_bytes - 1)
        assert len(reads) == 6  # init + 5 segments

    def test_out_of_bounds(self, layout, stream_info):
        reads = map_range_to_segments(layout, stream_info.total_bytes, stream_info.total_bytes + 100)
        assert len(reads) == 0


# ---------------------------------------------------------------------------
# Position to segment index
# ---------------------------------------------------------------------------


class TestPositionToSegment:
    @pytest.fixture()
    def stream_info(self):
        return _sample_info()

    def test_start(self, stream_info):
        assert position_ms_to_segment_index(stream_info, 0) == 0

    def test_middle(self, stream_info):
        # 5 segments, 210000ms total → 42000ms each
        idx = position_ms_to_segment_index(stream_info, 50000)
        assert idx == 1  # 42000 < 50000 < 84000, so segment 1

    def test_end(self, stream_info):
        idx = position_ms_to_segment_index(stream_info, 209999)
        assert idx == 4  # last segment

    def test_beyond_end(self, stream_info):
        idx = position_ms_to_segment_index(stream_info, 999999)
        assert idx == 4  # clamped to last
