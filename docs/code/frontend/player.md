# Player

`components/PlayerBar.tsx` owns the single `<audio>` element. Its `src` is always the local
endpoint `http://127.0.0.1:<port>/api/stream/<id>/audio`; the browser handles buffering and
seeking by sending Range requests ([serving](../backend/serving.md)).

## Load sequence

When `state.currentSong` changes, `load(song)` runs:

```ts
const gen = ++loadGen.current;           // this load's generation
loadAbort.current?.abort();              // cancel the previous /play
const ctrl = new AbortController();

audio.pause(); audio.removeAttribute("src"); audio.load();   // stop the old song now

const info = await api.playSong(song.id, ctrl.signal);       // POST /play: resolves the stream
if (gen !== loadGen.current) return;     // a newer song was chosen meanwhile
store.setDurationMs(info.duration_ms);
audio.src = api.getStreamAudioUrl(song.id);
await audio.play();
```

Clicking five songs quickly fires five `/play` requests, but only the last one sets `audio.src`:
earlier ones are aborted or fail the generation check. The backend does the same on its side
(`_play_seq`), so the session also ends on the last song.

`duration_ms` from `/play` (exact, from the segment table) is shown until the element's own
`loadedmetadata` arrives. A spinner replaces the play button while loading.

The time from `load()` to the `playing` event is logged to the API relay as
`TTFA <id> <ms> cached=<bool>` (Logs → API relay). Typical values: ~25 ms when init and the first
segment are cached, 1.3–1.6 s for an uncached song.

## Segment bar

`/api/stream/{id}/chunks` is polled every 500 ms (with an in-flight guard) and drawn as one cell
per segment, sized by duration and coloured by status: `pending`, `downloading` (pulsing),
`downloaded`, `error`. Cell offsets are computed in a `useMemo`. Clicking the bar maps the x
position to a time and seeks:

```ts
audio.currentTime = t;                   // browser issues a Range request
api.seek(t * 1000);                      // backend bumps the epoch, buffers from there
```

Below it, `/api/stream/cache-info` (every 5 s) feeds the cache usage line.

## Persistence

`state.ts` saves `{songs, currentIndex, volume}` to `localStorage` under `amp.queue.v1`,
debounced 500 ms, inside try/catch (storage can be unavailable). On startup,
`player/persistence.ts` validates what it reads: song IDs must be 11-character YouTube IDs, the
index and volume are clamped, and anything malformed is dropped.

The restored song is shown **paused** and isn't loaded: `store.takeRestored()` tells the load
effect to skip it. The play button sees that the loaded ID doesn't match and calls `load()`.

## Next-song prefetch

```ts
// player/prefetch.ts
shouldPrefetch(positionMs, durationMs) =
  durationMs - positionMs < 20_000 || positionMs > 0.8 * durationMs;
```

The 2 s position tick checks this. The first time it's true for a song,
`POST /api/stream/buffer/<next>?mode=prefetch` is sent once. The backend resolves the next
song's stream and downloads its first segments at low priority, so the next `/play` returns in
milliseconds and playback starts from disk.

## Error handling

| Failure | Shown as |
|---|---|
| `/play` fails with a coded error | `describeError()`: e.g. `auth_required` → "Sign in required for this track", `node_missing` → "Node.js not found. Install it and restart." |
| `fetch` itself fails | "Backend not reachable" |
| `audio.play()` rejected (autoplay policy) | "Autoplay blocked — click play to start" |
| `<audio>` error after `src` was set | `describeMediaError(code)`: 1 aborted, 2 network, 3 decode, 4 format not supported |

On a **network error** (`MEDIA_ERR_NETWORK`) mid-song, the player reloads the source once per load
and resumes at `currentTime`. This pairs with the backend's rule of aborting the connection
rather than sending a short body when a segment fails. A second failure is shown to the user.

The texts live in `player/errors.ts`, next to the codes from `api/errors.py`. Keep them in sync.
