# Segment table

The **segment table** maps each segment of a song to a byte range of the YouTube file and a
duration. It's what lets AMP download pieces independently, seek precisely and serve the song as
one file. It is built once per song (single-flight) right after [extraction](extraction.md), in
`StreamingService._build_from_stream()`.

## Data types (`utils/layout.py`)

```python
@dataclass
class SegmentInfo:
    index: int           # 0..N-1 (the init segment is index -1, stored separately)
    byte_start: int
    byte_end: int        # inclusive
    duration_ms: int
    url: str

@dataclass
class StreamInfo:
    song_id: str
    title: str
    duration_ms: int
    mime_type: str               # audio/mp4 | audio/webm
    init_range: tuple[int, int]  # (0, -1) = no init segment
    segments: list[SegmentInfo]
    is_dash: bool                # True = exact table from the sidx ("method": "sidx")
    base_url: str
    itag: str
    total_bytes: int             # init + sum of segment sizes
    layout_id: str               # see "Cache identity" below
```

`is_dash` keeps its historical name for the API; `StreamInfo.method` returns `"sidx"` or
`"proportional"`.

## Exact table from the fMP4 `sidx`

itag 140 is a **fragmented MP4** file:

```
[ftyp][moov][sidx][moof][mdat][moof][mdat] … [moof][mdat]
└──────init──────┘└─segment 0─┘└─segment 1─┘   └─segment N-1─┘
```

The `sidx` box (Segment Index, ISO/IEC 14496-12 §8.16.3) lists the size and duration of every
fragment: an exact segment table, stored in the first kilobyte of the file.

1. `GET` the URL with `Range: bytes=0-65535` (`_fetch_head`, which never reads more than asked
   even if the CDN ignores Range).
2. `parse_fmp4_index(head)` (`utils/mp4.py`) walks the top-level boxes up to the `sidx`.
3. If the `moov` is bigger than 64 KB, the parser raises `NeedMoreData(n)` and the head is
   re-fetched with `n + 64 KB` bytes (at most twice; a short read means there is no sidx).
4. The head bytes already contain the init segment, so they're written as `init.bin`: the first
   play saves one request.

The **init segment** is everything before the first fragment (`ftyp + moov + sidx`), so
`init + segment 0 + … + segment N-1` is byte-for-byte the CDN file and
`total_bytes == filesize`. An integration test (`test_concat_equals_cdn_file`) checks the sha256
of both.

A typical song: init ≈ 1 KB, then ~10 s fragments (26 segments for a 258 s song).

??? abstract "Parser details (`utils/mp4.py`)"
    Pure functions, unit-tested with synthetic boxes and a real header
    (`tests/fixtures/itag140_head.bin`, the first 1,012 bytes of `BAgTQhR8MLo`).

    - **Boxes** (`iter_boxes`): 32-bit size + 4-char type; `size == 1` → a 64-bit size follows;
      `size == 0` → the box runs to the end of the file. Only boxes before the first `moof` are
      read; `moof`/`mdat` are never parsed.
    - **`sidx`** (`parse_sidx`): full box header, `reference_ID`, `timescale`,
      `earliest_presentation_time` + `first_offset` (32-bit in version 0, 64-bit in version 1),
      `reference_count`, then per reference: 1-bit type + 31-bit size, 32-bit duration, SAP fields.
      Hierarchical indexes (`reference_type == 1`) are rejected.
    - The first fragment starts at `sidx_offset + sidx_size + first_offset`; each following one
      right after the previous. `init_end = first_fragment − 1`.
    - **Durations are rounded cumulatively** (`elapsed × 1000 // timescale` at each boundary), so
      they add up exactly to the total instead of drifting by a millisecond per segment.

    `scripts/dump_boxes.py` prints the boxes of a real stream's head, useful when YouTube changes
    its files.

### Sanity checks → fallback

The sidx table is rejected, and the proportional fallback used, when:

- the container isn't m4a/mp4 (WebM keeps its index in `Cues`, which isn't parsed);
- there's no `sidx` before the first fragment, or it's hierarchical;
- the head fetch fails (HTTP error);
- the sidx sizes don't add up to the extracted `filesize`.

A WARNING is logged if the sidx durations differ from yt-dlp's duration by more than 1 s (the
table is still used).

## Proportional fallback

For WebM (itag 251) or MP4 without a usable sidx: the file is split into byte ranges of about
`SEGMENT_TARGET_SEC` (5 s) each, from the extracted size and duration. There's no init segment
(`init_range = (0, -1)`).

- Size: `filesize` from extraction, else the URL's `clen=`, else a `HEAD` / `Range: bytes=0-0` probe.
- Duration: from extraction. **Unknown duration = unplayable** (there's no default).

Everything downstream works the same, but time → segment mapping is approximate, so seeks may
land a little off.

## Cache identity (`layout_id`)

Segment files are only valid for the byte layout they were cut from. If YouTube serves a
different file (a refresh picked itag 251 instead of 140, or the file was re-encoded), old
segments must not be mixed with new ones.

```python
layout_id = sha256(f"{itag}|{total_bytes}|{n_segments}|{method}")[:16]
```

Each song directory holds `layout.json` (written atomically):

```json
{"layout_id": "…", "method": "sidx", "itag": "140", "mime_type": "audio/mp4",
 "total_bytes": 4172237, "duration_ms": 257613, "init_range": [0, 1011],
 "segments": [[byte_start, byte_end, duration_ms], …]}
```

When a freshly built table has a **different** `layout_id`, `CacheStore.apply_layout()` purges the
song's directory, its DB rows and its registry entries, then writes the new manifest.
A download that was in flight under the old layout is discarded when it completes. At startup,
directories without `layout.json` are deleted ([reconciliation](cache.md#startup-reconciliation)).

## Byte-range math

Used by the audio endpoint ([serving](serving.md)):

- `build_virtual_layout(info)` → `[(virt_start, virt_end, seg_index, file_offset), …]`, the
  song seen as one file: `[init][seg 0][seg 1]…`.
- `map_range_to_segments(layout, a, b)` → which files to read, and which bytes inside each, for
  the virtual range `[a, b]`. A range can span several segments.
- `position_ms_to_segment_index(info, ms)` → the segment containing a playback position
  (cumulative durations).
