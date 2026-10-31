"""Unit tests for services/streaming/playback.py — PlaybackSession + buffer_plan."""

from backend.services.streaming.playback import PlaybackInfo, PlaybackSession, buffer_plan
from backend.services.streaming.registry import Priority
from backend.utils.layout import SegmentInfo, StreamInfo

SONG = "dQw4w9WgXcQ"


def _info(n, seg_ms=5000, has_init=True):
    segs = [SegmentInfo(i, 100 + i * 10, 109 + i * 10, seg_ms, "u") for i in range(n)]
    return StreamInfo(song_id=SONG, title="", duration_ms=n * seg_ms, mime_type="audio/mp4",
                      init_range=(0, 99) if has_init else (0, -1), segments=segs)


class TestPlaybackInfo:
    def test_to_dict(self):
        d = PlaybackInfo(song_id="test", position_ms=5000, is_playing=True, volume=0.8, epoch=3,
                         last_updated=1234.5).to_dict()
        assert d == {"song_id": "test", "current_segment_index": 0, "position_ms": 5000, "is_playing": True,
                     "volume": 0.8, "epoch": 3, "last_updated": 1234.5}


class TestBufferPlan:
    def test_relative_to_playhead(self):
        plan = buffer_plan(_info(60), 40, 30_000)
        assert plan == [(-1, Priority.CRITICAL), (40, Priority.CRITICAL), (41, Priority.HIGH),
                        (42, Priority.HIGH)] + [(i, Priority.NORMAL) for i in range(43, 47)]

    def test_stops_at_last_segment(self):
        assert [i for i, _ in buffer_plan(_info(60), 58, 30_000)] == [-1, 58, 59]

    def test_no_init(self):
        assert buffer_plan(_info(3, has_init=False), 0, 30_000)[0] == (0, Priority.CRITICAL)


class TestPlaybackSession:
    def test_should_buffer_once_per_segment(self):
        s = PlaybackSession()
        s.start(SONG, 0)
        assert s.should_buffer(SONG, 3, 0) is True
        assert s.should_buffer(SONG, 3, 0) is False
        assert s.should_buffer(SONG, 4, 0) is True
        assert s.should_buffer(SONG, 4, 1) is True  # a seek (new epoch) always buffers

    def test_protected(self):
        s = PlaybackSession()
        assert s.protected() is None
        s.start(SONG, 0)
        s.set_position(12_000, 2)
        assert s.protected() == (SONG, 2)
        assert s.stop() == SONG
        assert s.protected() is None

    def test_snapshot_is_a_copy(self):
        s = PlaybackSession()
        s.start(SONG, 0)
        snap = s.snapshot()
        s.set_playing(False)
        assert snap.is_playing is True
