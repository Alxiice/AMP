# Phase 2 — Real segment table from the fMP4 index

**Goal**: replace the guessed, proportional byte split with an **exact** segment table: real byte ranges and real durations, read from the stream's own index. Then make the on-disk cache safe when the underlying format changes.

**Effort**: 1–2 days · **Depends on**: Phase 1 · **Branch**: `fix/phase-2-segment-table`

**Spec deviation**: DESIGN_DOC_2.md §6.2–6.3 expects a DASH **MPD**. In practice yt-dlp returns direct media URLs, and the MPD branch never ran (every log line is "Progressive fallback"). This phase reads the index from inside the media file instead. Update §6.2–6.4 and the glossary when the phase lands.

---

## 1. Problems addressed

| # | Problem | Evidence |
|---|---|---|
| F4 | No song ever gets a real segment table. Segments are `filesize / (duration / 5 s)` byte slices, so time→segment mapping is approximate even with the correct duration from Phase 1. | `streaming.py:506-550`, `streaming.log` |
| — | `dash.py` MPD parsing (≈250 lines plus tests) is dead code in production | no "DASH manifest parsed" line in any log |
| — | **Cache identity**: segment files are keyed only by `(song_id, index)`. If a refresh picks a different format (itag 140 → 251) or the file size changes, old and new segments mix on disk and the concatenated stream is corrupt. | `_segment_path`, `Segment` model |

---

## 2. Background: why the index is in the file

YouTube's itag 140 (AAC) is a **fragmented MP4** stored on the CDN as one file:

```
[ftyp][moov (with mvex)][sidx][moof][mdat][moof][mdat] …
```

The `sidx` (Segment Index) box lists every fragment: its byte size and its duration in timescale units. That is exactly what `SegmentInfo` needs. A single range request for the first ~64 KB returns `ftyp + moov + sidx`.

Itag 251 (WebM/Opus) keeps a similar index in its `Cues` element. **WebM is out of scope**: it keeps using the proportional fallback, now with correct size and duration from Phase 1.

---

## 3. Tasks

### 2.0 Spike: confirm the box layout (do this first, ~1 h)

- Write a throwaway script, `scripts/dump_boxes.py`, that extracts itag 140 for the two pinned songs, range-fetches bytes `0-65535`, and prints the top-level boxes (`type`, `offset`, `size`).
- **Go**: `sidx` is present before the first `moof`. Continue with 2.1.
- **No-go**: no `sidx`. Stop here: keep the proportional fallback, do only 2.4–2.6, and record the result in AGENTS.md.
- Save one real header as a test fixture: `backend/tests/fixtures/itag140_head.bin` (the bytes up to the end of `sidx`, a few KB). It is media metadata only, with no signatures or cookies.

### 2.1 Pure MP4 box parser — new `amp/backend/utils/mp4.py`

```python
@dataclass(frozen=True)
class Mp4Index:
    init_end: int            # inclusive; bytes [0, init_end] = everything before the first fragment
    timescale: int
    segments: list[tuple[int, int, int]]   # (byte_start, byte_end, duration_ms), absolute file offsets

def iter_boxes(buf: bytes, start: int = 0) -> Iterator[tuple[str, int, int]]   # (type, offset, size)
def parse_sidx(buf: bytes, offset: int) -> tuple[int, int, list[tuple[int, int]]]  # timescale, first_offset, [(size, duration)]
def parse_fmp4_index(head: bytes) -> Mp4Index   # raises NeedMoreData(n) / ValueError
```

- **Box header**: 32-bit size + 4-char type. `size == 1` → a 64-bit `largesize` follows; `size == 0` → the box runs to the end of the file.
- **`sidx` (ISO/IEC 14496-12 §8.16.3)**: full box (version, flags), `reference_ID`, `timescale`, then `earliest_presentation_time` and `first_offset` (32-bit if version 0, 64-bit if version 1), 16 reserved bits, a 16-bit `reference_count`, then for each reference: 1-bit `reference_type` + 31-bit `referenced_size`, 32-bit `subsegment_duration`, 32-bit SAP fields.
  - The first fragment starts at `sidx_offset + sidx_size + first_offset`. Each following fragment starts right after the previous one.
  - Reject `reference_type == 1` (hierarchical index) with `ValueError`. YouTube audio doesn't use it.
- **`init_end` = (first fragment offset) − 1.** The init range therefore covers `ftyp + moov + sidx`, so **the virtual file is byte-for-byte the CDN file** and `total_bytes == filesize`. Keep that invariant: it makes Range math and debugging trivial.
- If `head` ends before `sidx` is complete, raise `NeedMoreData(required_len)`. The caller re-fetches `0..required_len-1`.

### 2.2 Use the index in `StreamingService._build_stream_info`

```
stream = extractor.get(song_id)
if stream.ext in ("m4a", "mp4"):
    head = range_get(stream.url, 0, 65535)            # retry once with NeedMoreData.required_len
    try:   idx = parse_fmp4_index(head);  return StreamInfo(… is_dash=True …)
    except ValueError:  log WARNING, fall through
return build_proportional_info(stream)               # Phase 1 metadata, is_dash=False
```

- Keep the name `is_dash` for API compatibility, but document it as "exact segment table" (`True`) vs "proportional" (`False`).
- Cache the downloaded head bytes as `init.bin` if they already cover `[0, init_end]`. That saves one request on first play.
- Check that `sum(duration_ms) ≈ stream.duration_ms` (±1 s). Log a WARNING if not, but don't fail.

### 2.3 Remove the MPD code path

- Delete from `amp/backend/utils/dash.py`: `parse_mpd`, `_parse_segment_list`, `_parse_segment_template`, `_resolve_template`, `_parse_duration_to_ms`, `MPD_NS`, `_q`.
- Keep `SegmentInfo`, `StreamInfo`, `build_virtual_layout`, `map_range_to_segments`, `position_ms_to_segment_index`. Rename the module to `amp/backend/utils/layout.py` and update the imports. (Optional; if you skip it, at least fix the module docstring.)
- Delete the MPD tests from `test_dash.py` and keep the layout and Range-math tests (rename to `test_layout.py` if the module is renamed).
- Remove the XML-sniffing branch (`is_xml`) from `_build_stream_info`.

### 2.4 Cache identity

- Add `layout_id: str` to `StreamInfo`: a short hash of `(itag, total_bytes, len(segments), method)`, where `method` is `"sidx"` or `"proportional"`.
- Store one manifest per cached song: `.amp/cache/segments/{song_id}/layout.json` → `{layout_id, itag, mime_type, total_bytes, duration_ms, segments: [[start, end, dur], …]}`. Write it atomically (P15).
- When `_build_stream_info` produces a `layout_id` that differs from the one on disk, **purge the song's directory and DB rows**, then write the new manifest. Log at INFO.
- `reconcile_cache()`: a song directory without `layout.json` is treated as orphaned and deleted. This also clears all caches written before Phase 2, which use the incompatible proportional layout.
- **Bonus (optional)**: with `layout.json` present, a cached song can be served **without any extraction** after restart, as long as every segment the player needs is on disk. That makes replaying a cached song instant, which is the cached-playback part of goal G1. Only call the extractor when a missing segment has to be downloaded.

### 2.5 DB model

- Add `layout_id` (String(16), nullable) to `Segment`. There is no migration tool: `init_db()` uses `create_all`, which does not alter existing tables. Simplest option: on startup, if the column is missing, drop and recreate the `segments` table (it is only a cache) and let reconciliation delete the files.

### 2.6 Update the spec

- DESIGN_DOC_2.md §6.2: replace "Getting the manifest URL" with "Getting the stream URL + index".
- §6.3: describe `sidx` parsing; mention MPD only as historical.
- §6.4: progressive fallback is now WebM-only (or used when no `sidx` is found).
- §6.6: document `layout.json` and cache identity.

---

## 4. Tests to add

| Test | Asserts |
|---|---|
| `test_iter_boxes_basic` / `_largesize` / `_size_zero` | synthetic buffers: correct types, offsets and sizes |
| `test_parse_sidx_v0` / `_v1` | synthetic `sidx`: timescale, first_offset, sizes, durations |
| `test_parse_fmp4_index_fixture` | `fixtures/itag140_head.bin`: `init_end` > 0, segments contiguous, `segments[0].start == init_end + 1`, durations sum ≈ the known song length |
| `test_need_more_data` | truncated head raises `NeedMoreData` with the correct `required_len` |
| `test_hierarchical_sidx_rejected` | `reference_type=1` raises `ValueError` |
| `test_virtual_layout_equals_file` | for an `Mp4Index`, `build_virtual_layout` virtual offsets == absolute file offsets |
| `test_layout_change_purges_song` | write segments under layout A; build info with layout B; directory purged and new manifest written |
| `test_reconcile_deletes_dir_without_manifest` | legacy directory (no `layout.json`) is deleted at startup |
| Integration: `test_concat_equals_cdn_file` | download all segments for a pinned song; `sha256(init + segments)` == `sha256` of a single full GET of the URL |

---

## 5. Acceptance criteria

- [ ] Spike 2.0 result recorded in AGENTS.md (go or no-go, with box listing).
- [ ] `GET /api/stream/info/{id}` for an itag 140 song returns `is_dash: true`, real segment count and per-segment durations. Durations sum to within ±1 s of the song length.
- [ ] Integration `test_concat_equals_cdn_file` passes for both pinned songs.
- [ ] Seeking to 50% in the UI starts playback within one segment of the target (check `current_segment_index` in `/api/stream/playback-state`).
- [ ] After the upgrade, the first startup deletes the pre-Phase-2 cache directories (logged by reconciliation).
- [ ] `grep -rn "parse_mpd" backend` returns nothing.

## 6. Risks and notes

- **The spike decides the scope.** If YouTube ever drops `sidx` from itag 140, the proportional fallback with correct metadata (from Phase 1) still works. The work in this phase is just smaller.
- **Segment count changes the SegmentBar.** YouTube fragments are usually larger than 5 s, so there are fewer cells than before. That's expected. Phase 4 adjusts the rendering if needed.
- **Don't parse `mdat`/`moof`.** Only the boxes in front of the first fragment matter here.
