"""Unit tests for utils/dash.py — MPD parser, byte-range math, range mapping.

Fully mocked, no network. Uses fixture MPD XML strings.
"""

import pytest

from backend.utils.dash import (
    StreamInfo,
    SegmentInfo,
    build_virtual_layout,
    map_range_to_segments,
    parse_mpd,
    position_ms_to_segment_index,
    _parse_range,
    _parse_duration_to_ms,
    _resolve_template,
)


# ---------------------------------------------------------------------------
# Fixtures: MPD XML strings
# ---------------------------------------------------------------------------

MPD_SEGMENT_LIST = """<?xml version="1.0" encoding="UTF-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" mediaPresentationDuration="PT3M30.000S" type="static">
  <Period id="0" start="PT0S" duration="PT210S">
    <AdaptationSet id="0" contentType="audio" mimeType="audio/mp4" segmentAlignment="true">
      <Representation id="140" bandwidth="128000" codecs="mp4a.40.2" mimeType="audio/mp4" audioSamplingRate="44100">
        <AudioChannelConfiguration schemeIdUri="urn:mpeg:dash:23003:3:audio_channel_configuration:2011" value="2"/>
        <BaseURL>https://rr1---sn-example.googlevideo.com/videoplayback?expire=123</BaseURL>
        <SegmentList timescale="1000" duration="5000">
          <Initialization range="0-623"/>
          <SegmentURL mediaRange="624-50623"/>
          <SegmentURL mediaRange="50624-101223"/>
          <SegmentURL mediaRange="101224-151823"/>
          <SegmentURL mediaRange="151824-202423"/>
          <SegmentURL mediaRange="202424-253023"/>
        </SegmentList>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>"""

MPD_SEGMENT_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" mediaPresentationDuration="PT3M30.000S" type="static">
  <Period id="0" start="PT0S">
    <AdaptationSet id="0" contentType="audio" mimeType="audio/webm">
      <Representation id="251" bandwidth="160000" codecs="opus" mimeType="audio/webm">
        <BaseURL>https://rr1---sn-example.googlevideo.com/videoplayback</BaseURL>
        <SegmentTemplate timescale="1000" initialization="init-$RepresentationID$.$Ext$" media="seg-$RepresentationID$-$Number%05d$.$Ext$" startNumber="1" indexRange="0-350">
          <SegmentTimeline>
            <S t="0" d="5000" r="3"/>
            <S t="20000" d="5000" r="1"/>
          </SegmentTimeline>
        </SegmentTemplate>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>"""

MPD_NO_AUDIO = """<?xml version="1.0"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011">
  <Period>
    <AdaptationSet contentType="video" mimeType="video/mp4">
      <Representation id="137" bandwidth="1000000" codecs="avc1.640028"/>
    </AdaptationSet>
  </Period>
</MPD>"""

INVALID_XML = "not xml at all <<<"


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestParseRange:
    def test_valid_range(self):
        assert _parse_range("0-623") == (0, 623)

    def test_large_range(self):
        assert _parse_range("1000000-2000000") == (1000000, 2000000)

    def test_none(self):
        assert _parse_range(None) is None

    def test_empty(self):
        assert _parse_range("") is None

    def test_invalid_format(self):
        assert _parse_range("abc") is None
        assert _parse_range("0") is None
        assert _parse_range("0-") is None


class TestParseDuration:
    def test_seconds(self):
        assert _parse_duration_to_ms("PT30S") == 30000

    def test_minutes_seconds(self):
        assert _parse_duration_to_ms("PT3M30S") == 210000

    def test_hours(self):
        assert _parse_duration_to_ms("PT1H2M3S") == 3723000

    def test_fractional(self):
        assert _parse_duration_to_ms("PT3M30.500S") == 210500

    def test_empty(self):
        assert _parse_duration_to_ms("") == 0
        assert _parse_duration_to_ms(None) == 0

    def test_invalid(self):
        assert _parse_duration_to_ms("garbage") == 0


class TestResolveTemplate:
    def test_basic_tokens(self):
        result = _resolve_template(
            "init-$RepresentationID$-$Number%05d$.$Ext$",
            "140", 128000, "mp4", number=42,
        )
        assert result == "init-140-00042.mp4"

    def test_bandwidth(self):
        result = _resolve_template("$Bandwidth$/seg", "140", 128000, "mp4")
        assert result == "128000/seg"

    def test_time_token(self):
        result = _resolve_template("$Time$", "140", 128000, "mp4", time=5000)
        assert result == "5000"


# ---------------------------------------------------------------------------
# MPD parser tests — SegmentList form
# ---------------------------------------------------------------------------


class TestParseMpdSegmentList:
    def test_basic_parse(self):
        info = parse_mpd(MPD_SEGMENT_LIST, song_id="dQw4w9WgXcQ", title="Test Song")
        assert info.song_id == "dQw4w9WgXcQ"
        assert info.title == "Test Song"
        assert info.is_dash is True
        assert info.mime_type == "audio/mp4"

    def test_duration(self):
        info = parse_mpd(MPD_SEGMENT_LIST, song_id="dQw4w9WgXcQ")
        assert info.duration_ms == 210000  # 3m30s

    def test_init_range(self):
        info = parse_mpd(MPD_SEGMENT_LIST, song_id="dQw4w9WgXcQ")
        assert info.init_range == (0, 623)

    def test_segment_count(self):
        info = parse_mpd(MPD_SEGMENT_LIST, song_id="dQw4w9WgXcQ")
        assert len(info.segments) == 5

    def test_segment_byte_ranges(self):
        info = parse_mpd(MPD_SEGMENT_LIST, song_id="dQw4w9WgXcQ")
        assert info.segments[0].byte_start == 624
        assert info.segments[0].byte_end == 50623
        assert info.segments[1].byte_start == 50624
        assert info.segments[1].byte_end == 101223
        assert info.segments[4].byte_start == 202424
        assert info.segments[4].byte_end == 253023

    def test_segment_indices(self):
        info = parse_mpd(MPD_SEGMENT_LIST, song_id="dQw4w9WgXcQ")
        for i, seg in enumerate(info.segments):
            assert seg.index == i

    def test_total_bytes(self):
        info = parse_mpd(MPD_SEGMENT_LIST, song_id="dQw4w9WgXcQ")
        # init: 624 bytes (0-623) + 5 segments
        init_size = info.init_range[1] - info.init_range[0] + 1
        seg_sizes = sum(s.byte_end - s.byte_start + 1 for s in info.segments)
        assert info.total_bytes == init_size + seg_sizes

    def test_base_url(self):
        info = parse_mpd(MPD_SEGMENT_LIST, song_id="dQw4w9WgXcQ")
        assert "googlevideo.com" in info.base_url


# ---------------------------------------------------------------------------
# MPD parser tests — SegmentTemplate + Timeline form
# ---------------------------------------------------------------------------


class TestParseMpdSegmentTemplate:
    def test_basic_parse(self):
        info = parse_mpd(MPD_SEGMENT_TEMPLATE, song_id="test12345678")
        assert info.is_dash is True
        assert info.mime_type == "audio/webm"  # opus codec

    def test_segment_count_with_repeats(self):
        # S t=0 d=5000 r=3 → 4 segments, S t=20000 d=5000 r=1 → 2 segments = 6 total
        info = parse_mpd(MPD_SEGMENT_TEMPLATE, song_id="test12345678")
        assert len(info.segments) == 6

    def test_segment_durations(self):
        info = parse_mpd(MPD_SEGMENT_TEMPLATE, song_id="test12345678")
        for seg in info.segments:
            assert seg.duration_ms == 5000  # 5000ms = 5s at timescale=1000

    def test_init_range(self):
        info = parse_mpd(MPD_SEGMENT_TEMPLATE, song_id="test12345678")
        assert info.init_range == (0, 350)


# ---------------------------------------------------------------------------
# MPD parser — error cases
# ---------------------------------------------------------------------------


class TestParseMpdErrors:
    def test_invalid_xml(self):
        with pytest.raises(ValueError, match="Invalid MPD XML"):
            parse_mpd(INVALID_XML, song_id="test12345678")

    def test_no_audio_adaptation(self):
        # Should still work — falls back to first AdaptationSet
        # But if there are no segments, it should raise
        with pytest.raises(ValueError):
            parse_mpd(MPD_NO_AUDIO, song_id="test12345678")

    def test_bytes_input(self):
        info = parse_mpd(MPD_SEGMENT_LIST.encode("utf-8"), song_id="dQw4w9WgXcQ")
        assert len(info.segments) == 5


# ---------------------------------------------------------------------------
# Virtual layout + range mapping
# ---------------------------------------------------------------------------


class TestVirtualLayout:
    @pytest.fixture()
    def stream_info(self):
        return parse_mpd(MPD_SEGMENT_LIST, song_id="dQw4w9WgXcQ")

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
        return parse_mpd(MPD_SEGMENT_LIST, song_id="dQw4w9WgXcQ")

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
        return parse_mpd(MPD_SEGMENT_LIST, song_id="dQw4w9WgXcQ")

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
