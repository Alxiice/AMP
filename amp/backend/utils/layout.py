"""Segment table types + byte-range math — pure functions, fully unit-testable.

A StreamInfo describes one audio resource as an optional init segment followed
by media segments, each an exact byte range of the CDN file. For itag 140 the
table comes from the fMP4 sidx (utils/mp4.py); otherwise it is a proportional
split by size and duration. The virtual file (init + segments) is what the
audio endpoint serves with HTTP Range support.

(Until Phase 2 this module was utils/dash.py and also parsed DASH MPDs; yt-dlp
never returned one, so that path was removed.)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import List, Tuple

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SegmentInfo:
    index: int            # 0..N-1 (init is index -1, stored separately)
    byte_start: int
    byte_end: int         # inclusive
    duration_ms: int
    url: str              # resource URL (range applied via header)


@dataclass
class StreamInfo:
    song_id: str
    title: str
    duration_ms: int
    mime_type: str        # audio/mp4 or audio/webm
    init_range: Tuple[int, int]
    segments: List[SegmentInfo] = field(default_factory=list)
    total_bytes: int = 0  # exact: init + sum(segment sizes)
    is_dash: bool = True  # True = exact segment table (sidx), False = proportional split
    base_url: str = ""
    itag: str = ""
    layout_id: str = ""   # cache identity, see compute_layout_id()

    @property
    def has_init(self) -> bool:
        """True if there is a real init segment (init_range end >= start).
        (0, -1) means no init segment — used for proportional streams."""
        return self.init_range[1] >= self.init_range[0]

    @property
    def init_size(self) -> int:
        """Size of the init segment in bytes (0 if none)."""
        if not self.has_init:
            return 0
        return self.init_range[1] - self.init_range[0] + 1

    @property
    def method(self) -> str:
        return "sidx" if self.is_dash else "proportional"

    def __post_init__(self) -> None:
        if not self.total_bytes:
            self.total_bytes = self.init_size + sum(s.byte_end - s.byte_start + 1 for s in self.segments)
        if not self.layout_id:
            self.layout_id = compute_layout_id(self.itag, self.total_bytes, len(self.segments), self.method)


def compute_layout_id(itag: str, total_bytes: int, n_segments: int, method: str) -> str:
    """Short hash identifying a byte layout; segments cached under another id are invalid."""
    key = f"{itag}|{total_bytes}|{n_segments}|{method}".encode()
    return hashlib.sha256(key).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Byte-range math utilities (used by the audio endpoint)
# ---------------------------------------------------------------------------


def build_virtual_layout(stream_info: StreamInfo) -> List[Tuple[int, int, int, int]]:
    """Build the virtual byte layout: list of (virt_start, virt_end, seg_index, file_offset).

    virt_start/virt_end are inclusive offsets in the virtual concatenated file.
    seg_index -1 = init segment.
    Returns entries ordered by virtual offset.
    """
    layout: List[Tuple[int, int, int, int]] = []
    offset = 0

    # Init segment (skip if no init — e.g. proportional streams with init_range=(0,-1))
    if stream_info.has_init:
        init_sz = stream_info.init_size
        layout.append((offset, offset + init_sz - 1, -1, stream_info.init_range[0]))
        offset += init_sz

    for seg in stream_info.segments:
        size = seg.byte_end - seg.byte_start + 1
        if size > 0:
            layout.append((offset, offset + size - 1, seg.index, seg.byte_start))
            offset += size

    return layout


def map_range_to_segments(
    layout: List[Tuple[int, int, int, int]],
    req_start: int,
    req_end: int,
) -> List[Tuple[int, int, int, int, int, int]]:
    """Map a virtual byte range [req_start, req_end] to segment file reads.

    Returns list of (virt_start, virt_end, seg_index, file_offset, read_start, read_end)
    where read_start/read_end are offsets within the local file.
    """
    reads: List[Tuple[int, int, int, int, int, int]] = []
    for virt_start, virt_end, seg_index, file_offset in layout:
        # Intersection of [req_start, req_end] with [virt_start, virt_end]
        s = max(req_start, virt_start)
        e = min(req_end, virt_end)
        if s <= e:
            reads.append((s, e, seg_index, file_offset, s - virt_start, e - virt_start))
    return reads


def position_ms_to_segment_index(stream_info: StreamInfo, position_ms: int) -> int:
    """Map a playback position (ms) to the segment index containing it."""
    cumulative = 0
    for seg in stream_info.segments:
        cumulative += seg.duration_ms
        if position_ms < cumulative:
            return seg.index
    return max(0, len(stream_info.segments) - 1)
