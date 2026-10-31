"""Fragmented-MP4 index parsing — pure functions, fully unit-testable.

YouTube's itag 140 is one fMP4 file on the CDN:

    [ftyp][moov (with mvex)][sidx][moof][mdat][moof][mdat] …

The sidx (Segment Index, ISO/IEC 14496-12 §8.16.3) lists every fragment's
byte size and duration, which is an exact segment table. Only the boxes in
front of the first fragment are read; moof/mdat are never parsed.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Iterator, List, Tuple


class NeedMoreData(Exception):
    """The buffer ends before the index is complete; re-fetch [0, required_len)."""

    def __init__(self, required_len: int) -> None:
        super().__init__(f"need {required_len} bytes")
        self.required_len = required_len


@dataclass(frozen=True)
class Mp4Index:
    init_end: int            # inclusive; bytes [0, init_end] = everything before the first fragment
    timescale: int
    segments: List[Tuple[int, int, int]]   # (byte_start, byte_end, duration_ms), absolute file offsets

    @property
    def total_bytes(self) -> int:
        return self.segments[-1][1] + 1 if self.segments else self.init_end + 1

    @property
    def duration_ms(self) -> int:
        return sum(d for _, _, d in self.segments)


def iter_boxes(buf: bytes, start: int = 0) -> Iterator[Tuple[str, int, int]]:
    """Yield (type, offset, size) for consecutive boxes from start.

    size == 1 → 64-bit largesize follows; size == 0 → box runs to the end of
    the file (reported here as running to the end of buf). Stops at the first
    header that doesn't fit in buf; the last box yielded may extend past buf.
    """
    pos = start
    while pos + 8 <= len(buf):
        size, kind = struct.unpack_from(">I4s", buf, pos)
        if size == 1:
            if pos + 16 > len(buf):
                return
            size = struct.unpack_from(">Q", buf, pos + 8)[0]
            if size < 16:
                raise ValueError(f"invalid largesize {size} at {pos}")
        elif size == 0:
            size = len(buf) - pos
        elif size < 8:
            raise ValueError(f"invalid box size {size} at {pos}")
        yield kind.decode("latin-1"), pos, size
        pos += size


def parse_sidx(buf: bytes, offset: int) -> Tuple[int, int, List[Tuple[int, int]]]:
    """Parse the sidx box at offset → (timescale, first_offset, [(size, duration)]).

    Raises NeedMoreData if buf ends inside the box, ValueError on a
    hierarchical index (reference_type 1) or a malformed box.
    """
    if offset + 8 > len(buf):
        raise NeedMoreData(offset + 8)
    size, kind = struct.unpack_from(">I4s", buf, offset)
    header = 8
    if size == 1:
        if offset + 16 > len(buf):
            raise NeedMoreData(offset + 16)
        size = struct.unpack_from(">Q", buf, offset + 8)[0]
        header = 16
    if kind != b"sidx":
        raise ValueError(f"expected sidx at {offset}, found {kind!r}")
    if size == 0 or size < header + 4:
        raise ValueError(f"invalid sidx size {size}")
    if offset + size > len(buf):
        raise NeedMoreData(offset + size)

    pos = offset + header
    version = buf[pos]
    pos += 4  # version (1) + flags (3)
    _reference_id, timescale = struct.unpack_from(">II", buf, pos)
    pos += 8
    if version == 0:
        _earliest, first_offset = struct.unpack_from(">II", buf, pos)
        pos += 8
    else:
        _earliest, first_offset = struct.unpack_from(">QQ", buf, pos)
        pos += 16
    _reserved, count = struct.unpack_from(">HH", buf, pos)
    pos += 4
    if pos + count * 12 > offset + size:
        raise ValueError(f"sidx reference_count {count} overflows box of {size} bytes")
    if timescale <= 0:
        raise ValueError("sidx timescale is 0")

    refs: List[Tuple[int, int]] = []
    for _ in range(count):
        word, duration, _sap = struct.unpack_from(">III", buf, pos)
        pos += 12
        if word >> 31:
            raise ValueError("hierarchical sidx (reference_type=1) not supported")
        refs.append((word & 0x7FFFFFFF, duration))
    return timescale, first_offset, refs


def parse_fmp4_index(head: bytes) -> Mp4Index:
    """Build the exact segment table from the head of an fMP4 file.

    init_end covers ftyp + moov + sidx, so the virtual file (init + segments)
    is byte-for-byte the CDN file. Raises NeedMoreData(n) if head ends before
    the sidx is complete, ValueError if there is no usable sidx.
    """
    for kind, offset, size in iter_boxes(head):
        if kind == "moof" or kind == "mdat":
            raise ValueError(f"no sidx before the first {kind} (at {offset})")
        if kind != "sidx":
            continue

        timescale, first_offset, refs = parse_sidx(head, offset)
        if not refs:
            raise ValueError("sidx has no references")
        start = offset + size + first_offset
        init_end = start - 1
        segments: List[Tuple[int, int, int]] = []
        elapsed = 0  # timescale units; round cumulatively so durations sum exactly
        for ref_size, duration in refs:
            if ref_size <= 0:
                raise ValueError("sidx reference with size 0")
            begin_ms = elapsed * 1000 // timescale
            elapsed += duration
            end_ms = elapsed * 1000 // timescale
            segments.append((start, start + ref_size - 1, end_ms - begin_ms))
            start += ref_size
        return Mp4Index(init_end=init_end, timescale=timescale, segments=segments)

    # Ran out of box headers before a sidx or a fragment: need the rest of the
    # last box plus the next header. (A caller whose re-fetch returns no more
    # bytes must treat a second NeedMoreData as "no sidx".)
    last_end = max((offset + size for _, offset, size in iter_boxes(head)), default=0)
    raise NeedMoreData(last_end + 8)
