# Phase 1 — Correct, single-flight stream extraction

**Goal**: each song gets **one** yt-dlp extraction, however many callers ask for it at once. That extraction tries a short, configurable list of player clients, picks the audio format in Python, and keeps the metadata later phases need: duration, file size, container, codec and URL expiry.

**Effort**: 1 day · **Depends on**: Phase 0 · **Branch**: `fix/phase-1-extraction`

---

## 1. Problems addressed

| # | Problem | Evidence |
|---|---|---|
| F2 | 12 "strategies" × an automatic retry without format = up to 24 extractions for a failing song. The format selector never affects *whether* a player response is obtained, only which format is returned. | `streaming.py:642-699`, `_try_extract` |
| F4 | Duration comes from the `songs` table, which search never fills, so it is always 180 s. File size comes from a `clen=1` probe that *appends* a parameter instead of reading the existing one. The MIME type is hard-coded to `audio/mp4`. | `streaming.py:513`, `:556`, `:540` |
| F5 | No per-song lock around `_get_stream_info`. `/play`, `/ready` (1 s poll), `/chunks` (500 ms poll), `/audio` and 4 workers race to build the same thing. On a CDN 403, each worker re-extracts. | log: 3 builds in the same second; `streaming.py:431`, `:1175` |
| — | `"best"`/`"worst"` fallbacks can return a muxed **video** format (e.g. itag 18) and treat it as audio | `_try_extract` filters on `acodec != "none"` only |
| — | `_extract_failures` dict is unbounded and unlocked | `streaming.py:269` |
| — | `streaming.py` is 1 588 lines and mixes extraction, downloading, caching and serving | — |

---

## 2. Target design

New module **`amp/backend/services/extractor.py`**. It has no FastAPI imports and no knowledge of segments.

```python
@dataclass(frozen=True)
class ExtractedStream:
    song_id: str
    url: str                  # googlevideo URL — never log it (P24)
    itag: str
    ext: str                  # "m4a" | "webm" | "mp4" …
    mime_type: str            # "audio/mp4" | "audio/webm"
    acodec: str
    is_audio_only: bool
    filesize: int | None      # bytes, from format["filesize"] or URL clen=
    duration_ms: int          # from info["duration"]
    title: str
    expires_at: float         # from URL expire=, minus a safety margin
    player_client: str        # which client succeeded (diagnostics)

class ExtractionError(Exception):
    code: str   # "unavailable" | "no_audio" | "auth_required" | "node_missing" | "extract_failed"
```

```python
class StreamExtractor:
    def get(self, song_id: str) -> ExtractedStream        # cached, single-flight
    def refresh(self, song_id: str, stale_url: str) -> ExtractedStream   # single-flight, see 1.5
```

`StreamingService` calls `StreamExtractor` and stops calling yt-dlp directly.

---

## 3. Tasks

### 1.1 Create `extractor.py` and move extraction out of `streaming.py`

- Move `build_ydl_opts` (from Phase 0), the cookie-file handling (P23: `0600`, deleted in `finally`), the format selection (`_select_audio_format`, added in Phase 0), the `available_at` wait (`_wait_until_available`, Phase 0) and the diagnostics into the new module.
- `StreamingService._get_stream_url`, `_extract_stream_url`, `_try_extract` and `_log_available_formats` are deleted. `refresh_stream_url` becomes a thin call to `StreamExtractor.refresh`.

### 1.2 One extraction per client, format chosen in Python

- *State after Phase 0*: the hard-coded list already starts with yt-dlp's default client (`None`), then `android`, `web_safari`, `tv_embedded`, `mweb` × 3 formats. Measured on 2026-10-31: default → TVHTML5 itag 140 with a ~5 s `available_at` delay; `android` (no PO token) → only itag 18. Keep the `available_at` wait for any client that sets it, and consider whether a client without the delay (e.g. the one yt-dlp picks without a JS runtime, VISIONOS) should come first to meet the TTFA target.
- New setting `YTDLP_PLAYER_CLIENTS: list[str] = ["default"]`, where `"default"` means "don't set `player_client`; use yt-dlp's built-in choice". Add other clients only after checking them against the current yt-dlp release notes, because client viability changes often.
- For each client in order:
  ```python
  opts = build_ydl_opts(client_or_None, fmt="bestaudio/best", cookie_file=…)
  opts["ignore_no_formats_error"] = True   # yt-dlp warns instead of raising "Requested format is not available"
  info = YoutubeDL(opts).extract_info(watch_url, download=False)
  stream = select_audio_format(info)       # pure function, see 1.3
  if stream: return stream
  ```
- Classify `DownloadError` text into `ExtractionError.code`:
  - "Video unavailable" or "Private video" → `unavailable`. Stop trying other clients.
  - "Sign in to confirm" or age-gated → `auth_required`. Try the next client; if none works, raise `auth_required`.
  - Anything else → `extract_failed`. Try the next client.
- Worst case is `len(YTDLP_PLAYER_CLIENTS)` extractions, not 24.
- `_log_available_formats` stays as a diagnostic, but it reuses the `info` already fetched instead of running another extraction.

### 1.3 `select_audio_format(info) -> ExtractedStream | None` (pure function)

Order of preference:

1. `format_id == settings.STREAM_FORMAT` (default `"140"`), audio-only, has `url`.
2. Audio-only (`vcodec in (None, "none")` and `acodec not in (None, "none")`), ext `m4a`/`mp4`, highest `abr`.
3. Audio-only, any container (e.g. 251 webm/opus), highest `abr`.
4. Nothing → `None`. **Never fall back to muxed video.** Leave a commented-out hook in case it's ever wanted, but don't enable it.

Fill these fields:

- `mime_type` from `ext`: m4a/mp4 → `audio/mp4`; webm → `audio/webm`.
- `filesize`: `format.get("filesize")`, then the `clen` query parameter of the URL, then `None`.
- `duration_ms`: `int(info["duration"] * 1000)`.
- `expires_at`: the `expire` query parameter (epoch seconds) minus 300 s. If it's missing, use `now + 5 h`.

### 1.4 Single-flight cache

- In `extractor.py`, implement a small generic `SingleFlight[K, V]`: a lock plus `dict[K, Future]`. The first caller for a key runs the function; concurrent callers block on the same `Future` and get the same result or exception.
- Positive cache: a `BoundedDict` of `song_id → ExtractedStream`, valid while `time.time() < expires_at`.
- Negative cache: a bounded, locked `song_id → (failed_at, ExtractionError)`. TTL is 5 min for `extract_failed` and 30 min for `unavailable`. `refresh()` clears it.
- Apply the same single-flight to `StreamingService._get_stream_info`, so building the stream info (extraction plus the HEAD/range probe) also runs once per song.

### 1.5 Refresh once per URL generation (P4)

- `refresh(song_id, stale_url)`: if the cached entry's URL differs from `stale_url`, another caller has already refreshed it, so return the cached entry. Otherwise, re-extract through the single-flight.
- In `_download_segment_with_retry`, pass the URL that got the 403. Four workers hitting a 403 at once then cause **one** extraction.
- If the refreshed stream has a different `itag` or `filesize` than before, the byte layout has changed. Phase 2 (cache identity) handles that. For now, log a WARNING.

### 1.6 Use the extracted metadata in `StreamingService`

- `_build_stream_info` gets `duration_ms`, `filesize`, `mime_type` and `title` from `ExtractedStream`.
  - Remove `_get_song_duration` and `_get_song_title`, which read the DB.
  - Remove the `180_000` fallback.
- `_probe_content_length` only runs when `filesize is None`. Drop strategy 1 (appending `clen=1`), and keep HEAD and `Range: bytes=0-0`.
- The progressive `StreamInfo.mime_type` comes from the extracted stream, not a literal.

### 1.7 Health reports extraction prerequisites

- `/api/health` gains `services.extractor: {"node": bool, "ejs": bool, "yt_dlp": "<version>"}`, computed once at startup.
- If `node` is missing, `StreamExtractor.get` raises `ExtractionError("node_missing")` straight away instead of running yt-dlp. Phase 4 shows this in the UI.

---

## 4. Tests to add

All tests mock `YoutubeDL`; none use the network.

| Test | Asserts |
|---|---|
| `test_select_prefers_itag_140` | formats [251, 140, 18] → itag 140, `audio/mp4` |
| `test_select_rejects_muxed_video` | formats [18, 22] only → `None` |
| `test_select_falls_back_to_opus` | formats [251, 18] → 251, `audio/webm` |
| `test_filesize_from_clen_param` | format without `filesize`, URL `…&clen=3623456&…` → 3623456 |
| `test_expires_at_from_url` | URL `expire=1767225600` → `expires_at == 1767225600 - 300` |
| `test_single_flight_one_extraction` | 10 threads call `get()` at once, `YoutubeDL.extract_info` called **once**, all get the same object |
| `test_single_flight_propagates_error` | the extraction raises; all 10 callers get the same `ExtractionError` |
| `test_negative_cache` | after a failure, `get()` within the TTL doesn't call yt-dlp; `refresh()` does |
| `test_refresh_dedup_by_stale_url` | 4 threads `refresh(id, old_url)` → 1 extraction |
| `test_unavailable_stops_client_rotation` | the first client raises "Video unavailable", so the second client is not tried |
| `test_stream_info_uses_extracted_duration` | `ExtractedStream(duration_ms=245_000, filesize=…)` → progressive segments cover 245 s, not 180 s |

---

## 5. Acceptance criteria

- [ ] Unit suite green. `extractor.py` has its own test file, `test_extractor.py`.
- [ ] `grep -n "YoutubeDL" backend/services/streaming.py` returns nothing.
- [ ] Playing a song from the UI logs exactly **one** "Extracted stream" line for that song, even with the segment bar polling.
- [ ] Two songs with different lengths produce different segment counts in `GET /api/stream/info/{id}`, and `duration_ms` matches YouTube's within 1 s.
- [ ] `test_integration_download.py` passes for both pinned songs.
- [ ] No googlevideo URL or cookie value appears in `app.log` or `streaming.log` (P24). Grep for `googlevideo` and `SAPISID=`.

## 6. Risks and notes

- **Client viability changes over time.** Keep `YTDLP_PLAYER_CLIENTS` in config so it can be tuned without code changes. Record the list that works in AGENTS.md.
- **`ignore_no_formats_error` returns `info` with an empty `formats` list** for some failures. `select_audio_format` must handle that (return `None`, then try the next client).
- **Don't persist `ExtractedStream` to disk.** URLs carry signatures (P24) and expire anyway.
