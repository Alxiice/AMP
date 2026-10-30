"""DASH MPD manifest parsing — pure functions, fully unit-testable.

Handles namespace ``urn:mpeg:dash:schema:mpd:2011``.
Supports two media-segment forms:
  1. SegmentList (what YouTube audio manifests use): SegmentURL@mediaRange
  2. SegmentTemplate + SegmentTimeline: S@t/d/r entries with optional mediaRange
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

MPD_NS = "urn:mpeg:dash:schema:mpd:2011"

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
    is_dash: bool = True
    base_url: str = ""

    @property
    def has_init(self) -> bool:
        """True if there is a real init segment (init_range end >= start).
        (0, -1) means no init segment — used for progressive streams."""
        return self.init_range[1] >= self.init_range[0]

    @property
    def init_size(self) -> int:
        """Size of the init segment in bytes (0 if none)."""
        if not self.has_init:
            return 0
        return self.init_range[1] - self.init_range[0] + 1

    def __post_init__(self) -> None:
        if not self.total_bytes:
            self.total_bytes = self.init_size + sum(s.byte_end - s.byte_start + 1 for s in self.segments)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _q(tag: str) -> str:
    """Qualify a tag with the MPD namespace."""
    return f"{{{MPD_NS}}}{tag}"


def _parse_range(r: Optional[str]) -> Optional[Tuple[int, int]]:
    """Parse 'start-end' into (start, end) inclusive. Returns None if invalid."""
    if not r:
        return None
    m = re.match(r"^(\d+)-(\d+)$", r.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _resolve_template(template: str, representation_id: str, bandwidth: int, ext: str,
                      number: Optional[int] = None, time: Optional[int] = None) -> str:
    """Resolve DASH template tokens: $RepresentationID$, $Bandwidth$, $Number$, $Time$, $Ext$."""
    result = template
    result = result.replace("$RepresentationID$", representation_id)
    result = result.replace("$Bandwidth$", str(bandwidth))
    result = result.replace("$Ext$", ext)
    if number is not None:
        result = result.replace("$Number$", str(number))
        result = result.replace("$Number%05d$", f"{number:05d}")
        result = result.replace("$Number%06d$", f"{number:06d}")
    if time is not None:
        result = result.replace("$Time$", str(time))
    return result


def _parse_duration_to_ms(duration: Optional[str]) -> int:
    """Parse ISO 8601 duration (PT#H#M#S) to milliseconds."""
    if not duration:
        return 0
    m = re.match(
        r"^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?"
        r"(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?$",
        duration.strip(),
    )
    if not m:
        return 0
    years, months, days, hours, minutes, seconds = m.groups()
    total_sec = (
        int(years or 0) * 365 * 86400
        + int(months or 0) * 30 * 86400
        + int(days or 0) * 86400
        + int(hours or 0) * 3600
        + int(minutes or 0) * 60
        + float(seconds or 0)
    )
    return int(total_sec * 1000)


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------


def parse_mpd(
    xml_data: str | bytes,
    song_id: str,
    title: str = "",
    duration_ms: int = 0,
    mime_hint: str = "audio/mp4",
) -> StreamInfo:
    """Parse a DASH MPD document into a StreamInfo segment table.

    Raises ValueError on unparseable XML or if no audio Representation is found.
    """
    if isinstance(xml_data, bytes):
        xml_data = xml_data.decode("utf-8")

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        raise ValueError(f"Invalid MPD XML: {e}") from e

    # Find the audio AdaptationSet
    audio_adaptation = None
    for adaptation in root.iter(_q("AdaptationSet")):
        content_type = adaptation.get("contentType", "")
        mime_type = adaptation.get("mimeType", "")
        if content_type == "audio" or mime_type.startswith("audio/"):
            audio_adaptation = adaptation
            break

    if audio_adaptation is None:
        # Fallback: first AdaptationSet
        for adaptation in root.iter(_q("AdaptationSet")):
            audio_adaptation = adaptation
            break

    if audio_adaptation is None:
        raise ValueError("No AdaptationSet found in MPD")

    # Find the audio Representation (prefer highest bandwidth)
    representations = list(audio_adaptation.iter(_q("Representation")))
    if not representations:
        raise ValueError("No Representation found in audio AdaptationSet")

    representation = representations[0]
    for rep in representations:
        bw = int(rep.get("bandwidth", "0"))
        if bw > int(representation.get("bandwidth", "0")):
            representation = rep

    rep_id = representation.get("id", "")
    rep_bw = int(representation.get("bandwidth", "0"))
    rep_mime = representation.get("mimeType", mime_hint)

    # BaseURL — walk up the tree (Representation-level > AdaptationSet-level > Period-level)
    base_url = ""
    rep_base = representation.find(_q("BaseURL"))
    if rep_base is not None and rep_base.text:
        base_url = rep_base.text.strip()
    else:
        as_base = audio_adaptation.find(_q("BaseURL"))
        if as_base is not None and as_base.text:
            base_url = as_base.text.strip()
        else:
            period_base = root.find(f".//{_q('Period')}/{_q('BaseURL')}")
            if period_base is not None and period_base.text:
                base_url = period_base.text.strip()

    # Determine mime type from codec
    codecs = representation.get("codecs", "")
    if "opus" in codecs.lower() or "vorbis" in codecs.lower():
        mime_type = "audio/webm"
    elif "mp4a" in codecs.lower() or "aac" in codecs.lower() or rep_mime == "audio/mp4":
        mime_type = "audio/mp4"
    else:
        mime_type = mime_hint

    # Total duration from MPD@mediaPresentationDuration or Period@duration
    if not duration_ms:
        mpd_dur = root.get("mediaPresentationDuration")
        if mpd_dur:
            duration_ms = _parse_duration_to_ms(mpd_dur)
        else:
            for period in root.iter(_q("Period")):
                pd = period.get("duration")
                if pd:
                    duration_ms = _parse_duration_to_ms(pd)
                    break

    # --- Init segment + media segments ---
    # (0, -1) = no init segment (end < start means empty range)
    init_range: Tuple[int, int] = (0, -1)
    segments: List[SegmentInfo] = []

    segment_list = representation.find(_q("SegmentList"))
    segment_template = representation.find(_q("SegmentTemplate"))

    if segment_list is not None:
        segments, init_range = _parse_segment_list(
            segment_list, base_url, rep_id, rep_bw, duration_ms
        )
    elif segment_template is not None:
        segments, init_range = _parse_segment_template(
            segment_template, base_url, rep_id, rep_bw, duration_ms
        )
    else:
        # Check AdaptationSet level
        as_seg_list = audio_adaptation.find(_q("SegmentList"))
        as_seg_template = audio_adaptation.find(_q("SegmentTemplate"))
        if as_seg_list is not None:
            segments, init_range = _parse_segment_list(
                as_seg_list, base_url, rep_id, rep_bw, duration_ms
            )
        elif as_seg_template is not None:
            segments, init_range = _parse_segment_template(
                as_seg_template, base_url, rep_id, rep_bw, duration_ms
            )

    if not segments:
        raise ValueError("No media segments found in MPD")

    # Re-index segments sequentially
    for i, seg in enumerate(segments):
        seg.index = i

    return StreamInfo(
        song_id=song_id,
        title=title,
        duration_ms=duration_ms,
        mime_type=mime_type,
        init_range=init_range,
        segments=segments,
        is_dash=True,
        base_url=base_url,
    )


def _parse_segment_list(
    seg_list: ET.Element,
    base_url: str,
    rep_id: str,
    rep_bw: int,
    total_duration_ms: int,
) -> Tuple[List[SegmentInfo], Tuple[int, int]]:
    """Parse SegmentList form: SegmentURL@mediaRange per segment."""
    segments: List[SegmentInfo] = []
    init_range: Tuple[int, int] = (0, -1)

    # Initialization
    init_el = seg_list.find(_q("Initialization"))
    if init_el is not None:
        range_str = init_el.get("range")
        if range_str:
            r = _parse_range(range_str)
            if r:
                init_range = r

    # Media segments
    seg_urls = list(seg_list.iter(_q("SegmentURL")))
    total_segs = len(seg_urls)
    default_dur = total_duration_ms // max(total_segs, 1) if total_segs else 0

    for i, seg_url in enumerate(seg_urls):
        media_range = seg_url.get("mediaRange")
        r = _parse_range(media_range)
        if r is None:
            # No range — individual file download (URL-based)
            url = seg_url.get("media", "")
            if not url and base_url:
                url = base_url
            segments.append(SegmentInfo(
                index=i,
                byte_start=0,
                byte_end=0,
                duration_ms=default_dur,
                url=url,
            ))
        else:
            segments.append(SegmentInfo(
                index=i,
                byte_start=r[0],
                byte_end=r[1],
                duration_ms=default_dur,
                url=base_url,
            ))

    return segments, init_range


def _parse_segment_template(
    seg_template: ET.Element,
    base_url: str,
    rep_id: str,
    rep_bw: int,
    total_duration_ms: int,
) -> Tuple[List[SegmentInfo], Tuple[int, int]]:
    """Parse SegmentTemplate + SegmentTimeline form."""
    segments: List[SegmentInfo] = []
    init_range: Tuple[int, int] = (0, -1)

    timescale = int(seg_template.get("timescale", "1"))
    duration_units = int(seg_template.get("duration", "0"))
    start_number = int(seg_template.get("startNumber", "1"))
    init_template = seg_template.get("initialization", "")
    media_template = seg_template.get("media", "")
    index_range_str = seg_template.get("indexRange", "")

    # Init segment
    if index_range_str:
        r = _parse_range(index_range_str)
        if r:
            init_range = r

    # SegmentTimeline
    timeline = seg_template.find(_q("SegmentTimeline"))
    if timeline is not None:
        seg_entries = list(timeline.iter(_q("S")))
        number = start_number
        cumulative_time = 0

        for s in seg_entries:
            t = int(s.get("t", str(cumulative_time)))
            d = int(s.get("d", str(duration_units)))
            r = int(s.get("r", "0"))  # repeat count

            media_range_str = s.get("mediaRange")
            cumulative_time = t

            for _ in range(r + 1):
                duration_ms = int(d * 1000 / timescale) if timescale else 0
                media_url = _resolve_template(media_template, rep_id, rep_bw, "mp4", number=number, time=t)

                if media_range_str:
                    rng = _parse_range(media_range_str)
                    if rng:
                        segments.append(SegmentInfo(
                            index=len(segments),
                            byte_start=rng[0],
                            byte_end=rng[1],
                            duration_ms=duration_ms,
                            url=base_url,
                        ))
                    else:
                        full_url = media_url if media_url.startswith("http") else (base_url + media_url if base_url else media_url)
                        segments.append(SegmentInfo(
                            index=len(segments),
                            byte_start=0,
                            byte_end=0,
                            duration_ms=duration_ms,
                            url=full_url,
                        ))
                else:
                    full_url = media_url if media_url.startswith("http") else (base_url + media_url if base_url else media_url)
                    segments.append(SegmentInfo(
                        index=len(segments),
                        byte_start=0,
                        byte_end=0,
                        duration_ms=duration_ms,
                        url=full_url,
                    ))

                number += 1
                cumulative_time += d

    return segments, init_range


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

    # Init segment (skip if no init — e.g. progressive streams with init_range=(0,-1))
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
