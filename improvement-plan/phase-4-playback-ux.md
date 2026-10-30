# Phase 4 — Playback UX & frontend

**Goal**: pressing play gives audio as fast as the backend allows, with no polling gate. Switching songs quickly never plays the wrong one. Failures show a specific reason. The queue and volume survive restarts, and the next song is warmed up before the current one ends.

**Effort**: 1 day · **Depends on**: Phase 3 · **Branch**: `fix/phase-4-playback-ux`

---

## 1. Problems addressed

| # | Problem | Where |
|---|---|---|
| F13 | After `POST /play`, the player polls `/ready` every **1 s** (up to 30×) before setting `audio.src`. That adds up to 1 s to time-to-first-audio (spec goal G1 is < 300 ms) and calls stream-info building on every poll. | `PlayerBar.tsx:98-140`, `endpoints.py:227-259` |
| F13 | The `waitForReady` loop is never cancelled. Click song A, then song B: A's loop can still set `audio.src` to A **after** B started. | `PlayerBar.tsx:106` |
| F17 | Invalid `song_id` → `ValueError` → **500**. | `validate_song_id` called in route bodies, no exception handler |
| — | `/audio` 404 returns an empty body with an audio content type, so the UI can only show "Audio error (code 4)" | `endpoints.py:292-307` |
| — | Queue, current index and volume are lost on restart. AGENTS.md says "settings persistence: done", but nothing is persisted. | `state.ts` |
| — | No gap reduction between songs: the next song's extraction only starts after `ended` | `state.ts:_onEnded` |
| — | `POST /stream/buffer/{id}` queues at CRITICAL/HIGH, so using it to warm the next song would compete with the current one | `streaming.py:381-386` |
| — | `components/SegmentBar.tsx` is unused (PlayerBar renders its own bar); per-render O(n²) offset computation in PlayerBar | `PlayerBar.tsx:360-363` |

---

## 2. API contract changes

### `POST /api/stream/{id}/play`, now a "resolve, then play" call

Blocks until stream info is resolved (Phase 1 single-flight, so cheap when cached), queues the buffer-ahead, then returns:

```jsonc
// 200
{ "song_id": "…", "duration_ms": 245000, "mime_type": "audio/mp4",
  "segment_count": 25, "is_dash": true, "epoch": 3 }
```

Errors use one shape everywhere (also for `/audio`, `/stream/info`, `/buffer`):

```jsonc
// 4xx/5xx
{ "detail": { "code": "unavailable", "message": "This video is unavailable." } }
```

| code | HTTP | Raised when |
|---|---|---|
| `invalid_id` | 400 | `validate_song_id` fails |
| `unavailable` | 404 | `ExtractionError("unavailable")` |
| `no_audio` | 404 | no audio-only format |
| `auth_required` | 401 | age-gated or members-only, signed out |
| `node_missing` | 503 | Phase 1 health check |
| `extract_failed` | 502 | everything else from the extractor |
| `segment_unavailable` | 502 | Phase 3 `ensure_segment` failure |

### `POST /api/stream/buffer/{id}?mode=prefetch`

`mode=prefetch` resolves the stream info and queues init plus the first 2 segments at **LOW** priority. It doesn't touch the playback session. The default mode (`current`) keeps today's behaviour.

### Removed: `GET /api/stream/{id}/ready`

---

## 3. Tasks

### 4.1 Backend error model

- New `amp/backend/api/errors.py`: an `ApiError(code, message, status)` exception plus FastAPI exception handlers for `ApiError`, `ValueError` from `validate_song_id`, and `ExtractionError`.
  - To keep `ValueError` handling narrow, make `validate_song_id` raise a dedicated `InvalidSongId(ValueError)`.
- Register the handlers in `create_app()`.
- `/audio`: drop the empty-body 404 special case and return the JSON error. The `<audio>` element fails either way; the UI now gets the reason from `/play`, before setting `src`.

### 4.2 `/play` contract and prefetch mode

- `StreamingService.start_playback` returns the summary above and raises `ExtractionError`/`ApiError` instead of logging and continuing.
- Add `mode` to `buffer_song` and a `prefetch(song_id)` method (init + 2 segments, `Priority.LOW`, current epoch).
- Delete the `/ready` route and `api.isStreamReady`.

### 4.3 PlayerBar load sequence with cancellation

File: `amp/frontend/src/components/PlayerBar.tsx` (extract into `src/player/loadSong.ts` if it grows)

```ts
const loadGen = useRef(0);

async function load(song: Song) {
  const gen = ++loadGen.current;
  setAudioError(null); setAudioLoading(true);
  try {
    const info = await api.playSong(song.id, { signal });      // resolves stream info
    if (gen !== loadGen.current) return;                       // a newer song was chosen
    audio.src = api.getStreamAudioUrl(song.id);
    await audio.play();
  } catch (e) {
    if (gen !== loadGen.current) return;
    setAudioError(describeError(e));                           // maps ApiError.code to user text
  } finally {
    if (gen === loadGen.current) setAudioLoading(false);
  }
}
```

- Use an `AbortController` for the `/play` fetch; abort it when a newer load starts.
- `describeError(code)` maps to short messages, e.g. `auth_required` → "Sign in required for this track", `node_missing` → "Node.js not found. Install it and restart."
- `fetchApi` parses `{detail: {code, message}}` into `ApiError.code`.

### 4.4 Measure time-to-first-audio (G1)

- In `load()`, record `performance.now()` at click and at the audio `playing` event. Send `TTFA <song_id> <ms> cached=<bool>` through `api.postLogs` and show it on the Logs page.
  - `cached` = whether `/play` reported all needed segments as present. Add `cached_ahead: bool` to the `/play` response.
- Record the cached and uncached numbers in AGENTS.md. Target: cached < 300 ms, uncached about extraction time + 1 segment.

### 4.5 Persist queue and volume

File: `amp/frontend/src/state.ts`

- Save `{songs, currentIndex, volume}` to `localStorage` key `amp.queue.v1`, debounced (500 ms), whenever they change. Wrap every read and write in `try/catch`.
- On startup, restore without autoplay: `currentSong` is set, the player shows it paused, and pressing play runs `load()`.
- Don't persist `positionMs` beyond an optional "resume from" hint. Leave that for later.

### 4.6 Prefetch the next song

- In `state.ts` `_onTimeUpdate`: when `remaining < 20 s` or `position > 80%`, and the next song hasn't been prefetched for this song yet, call `api.bufferAhead(next.id, "prefetch")` once.
- Reset the "prefetched" flag when `currentSong` changes.

### 4.7 Clean-ups

- Delete `components/SegmentBar.tsx` (unused).
- In PlayerBar, compute cumulative segment offsets once with `useMemo` over `segments` instead of `slice().reduce()` per cell.
- With the Phase 2 segment table, `duration_ms` from `/play` is accurate. Use it as `durationMs` until `loadedmetadata` arrives, so the time label isn't `0:00` while loading.
- The play button shows a spinner glyph while `audioLoading` (it currently shows ▶ in both states).

---

## 4. Tests to add

Backend (pytest, TestClient):

| Test | Asserts |
|---|---|
| `test_invalid_song_id_is_400` | `/api/stream/bad/play` → 400, `detail.code == "invalid_id"` |
| `test_play_returns_summary` | mocked extractor → 200 with `duration_ms`, `mime_type`, `segment_count` |
| `test_play_unavailable_is_404_coded` | extractor raises `unavailable` → 404 + code |
| `test_audio_error_is_json` | unresolvable stream → JSON body with code (not empty audio/mp4) |
| `test_prefetch_uses_low_priority` | `buffer?mode=prefetch` queues only init+2 at LOW; playback session unchanged |
| `test_ready_route_removed` | `/api/stream/{id}/ready` → 404 |

Frontend: there is no test runner yet. Optionally add `vitest` and test only the pure parts: `describeError`, the persistence (de)serialisation, and the prefetch threshold. Otherwise cover these with the manual checks below.

---

## 5. Acceptance criteria

- [ ] `npm run build` and the unit suite pass.
- [ ] Manual: click 5 different songs within 2 seconds. The **last** one plays, and the logs show no `audio.src` assignment for the earlier ones after the last.
- [ ] Manual: play an unavailable or region-locked ID → the player shows the specific message, not "code 4".
- [ ] Manual: restart the app → queue and volume restored, nothing auto-plays.
- [ ] Manual: let a song play to the end in a 2-song queue → the next song's `/play` returns immediately (already resolved) and TTFA is in the cached range.
- [ ] TTFA numbers (cached and uncached) recorded in AGENTS.md.
- [ ] `grep -rn "isStreamReady\|/ready" frontend/src backend` returns nothing.

## 6. Risks and notes

- **`/play` now blocks for the extraction time** (seconds on first play). The UI shows "Loading audio…". This is honest, and replaces a 1 s polling loop that hid the same wait.
- **Autoplay**: `audio.play()` after an `await` may lose the user-gesture context in some webviews. WebView2 allows it once the user has interacted with the app. Keep the existing `NotAllowedError` message as a fallback.
