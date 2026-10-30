# Phase 3 — Download pipeline correctness

**Goal**: every segment the player needs is either delivered or fails loudly. Seeks change priorities without losing work, two downloads of the same segment can't collide, and the cache evicts the least recently *used* segments.

**Effort**: 1–2 days · **Depends on**: Phase 2 · **Branch**: `fix/phase-3-download-pipeline`

---

## 1. Problems addressed

| # | Problem | Where |
|---|---|---|
| F6 | `DownloadManager._downloading` is filled at **enqueue** time, so it means "queued *or* in flight". After a seek bumps the epoch, `enqueue()` for an index that is still queued returns `False`. The worker then pops the old task, sees a stale epoch and drops it. The segment is not requested again until the next 2 s position report. | `streaming.py:225-238`, `:926-929` |
| F7 | `download_segment_sync` sees "is downloading" and polls the file for up to 30 s, even when the "download" is a queued task that will be dropped. On timeout, `_iter_audio_range` **silently skips** the segment, so the body is shorter than the declared `Content-Length` and the browser aborts. | `streaming.py:1126-1132`, `:1481-1494`, `:1467-1472` |
| F8 | Sync downloads aren't registered as in flight, so a worker can download the same segment at the same time. Both write `NNNN.tmp` (fixed name): on Windows `os.replace` can raise `PermissionError`, and a reader can see a partial file. | `streaming.py:1103`, `:1134-1137` |
| F11 | Eviction sorts by file **mtime** (download time). Serving a segment never updates it, and the DB `last_accessed` is written but never read, so this is FIFO, not LRU. `cleanup_cache()` also scans the whole cache directory after **every** segment download. | `streaming.py:1187-1259`, `:1166` |
| — | After eviction, in-memory status still says `DOWNLOADED` | `_seg_status` never downgraded |
| — | `get_all_segment_statuses` calls `path.exists()` for every segment on every 500 ms poll | `streaming.py:887-916` |
| — | `StreamingService` (~1 600 lines) mixes queueing, downloading, caching and serving | — |

---

## 2. Target design

Split `streaming.py` into focused modules (Phase 1 already moved extraction out):

```
services/streaming/
  __init__.py        # get_streaming_service(), StreamingService facade (public API unchanged)
  registry.py        # SegmentRegistry — single source of truth for per-segment state
  downloader.py      # DownloadManager (queue + workers) + fetch_segment() (HTTP + verify + atomic write)
  cache.py           # CacheStore — paths, size accounting, LRU eviction, reconciliation, layout.json
  serving.py         # serve_audio_range() + byte iterators
  playback.py        # PlaybackSession + buffer-ahead policy
```

### SegmentRegistry

Single source of truth, one lock:

```python
class SegState(Enum): MISSING, QUEUED, IN_FLIGHT, DONE, ERROR

@dataclass
class SegEntry:
    state: SegState
    priority: Priority | None     # best (lowest) priority requested so far while QUEUED
    epoch: int
    done: threading.Event          # set on DONE or ERROR, reset on re-queue
    error: str | None

class SegmentRegistry:
    def request(self, key, priority, epoch) -> bool        # True if a new heap entry should be pushed
    def claim(self, key, epoch) -> bool                    # worker/sync caller: QUEUED|MISSING -> IN_FLIGHT; False if someone else holds it
    def complete(self, key, ok: bool, error: str | None)   # IN_FLIGHT -> DONE|ERROR, sets event
    def evicted(self, key)                                 # DONE -> MISSING
    def wait(self, key, timeout) -> SegState
    def snapshot(self, song_id) -> list[SegState]          # for /chunks — no filesystem calls
```

Rules:

- **`request()`**:
  - `DONE` or `IN_FLIGHT`: no-op.
  - `QUEUED`: if the new request has a higher priority **or** a newer epoch, update the entry and push another heap item.
  - `MISSING` or `ERROR`: move to `QUEUED` and push.
- **Workers** pop heap items. If the entry is no longer `QUEUED` with that exact (priority, epoch), the item is a superseded duplicate and is skipped. Otherwise the worker `claim()`s and downloads.
- **Epoch now means priority, not cancellation**: a seek re-requests segments around the new playhead with a newer epoch, which outranks the old queued items. Downloads already in flight are allowed to finish (their bytes are valid). This replaces the "discard result" behaviour of P18, which never actually discarded anything because the file was written regardless. Update the P18 wording in DESIGN_DOC_2.md.

---

## 3. Tasks

### 3.1 Implement `SegmentRegistry` and wire `DownloadManager` to it

- Delete `DownloadManager._downloading`, `is_downloading`, `StreamingService._seg_status` and `set_segment_status`. All state lives in the registry.
- Keep the `SegmentTask` ordering of (priority, seq). Add the epoch to the task so a worker can tell whether its item has been superseded.

### 3.2 `ensure_segment(song_id, index, timeout) -> Path` for request handlers

Replaces `download_segment_sync`:

```
state = registry.get(key)
DONE       -> touch + return path
IN_FLIGHT  -> registry.wait(key, timeout); DONE -> path, else raise SegmentUnavailable
QUEUED/MISSING/ERROR -> if registry.claim(key, epoch): fetch in *this* thread (jumps the queue),
                        else wait as IN_FLIGHT
```

- No polling loop, no `time.sleep(0.05)`.
- `timeout` comes from a new setting, `SEGMENT_SYNC_TIMEOUT_S = 15`.
- A queued worker item for a key that a sync caller has claimed is skipped when popped, because `claim()` fails.

### 3.3 Unique temporary files (P15, F8)

- In `fetch_segment`: `fd, tmp = tempfile.mkstemp(dir=song_dir, prefix=f"{index:04d}.", suffix=".tmp")`, write, `fsync`, then `os.replace(tmp, final)`. Delete `tmp` in `finally` on failure.
- Reconciliation already deletes `*.tmp`. Keep that.

### 3.4 Audio serving never sends a short body (F7)

File: `serving.py`

- **Before returning the response**, call `ensure_segment` for the **first** segment of the requested range. If it fails, return a JSON error with an appropriate status (`502 segment_unavailable`, or `404`/`401` from the Phase 1 `ExtractionError` codes) instead of headers promising bytes.
- Inside the generator, for each later segment, call `ensure_segment`. On `SegmentUnavailable`, **raise**: Starlette then aborts the connection, which the browser treats as a network error it can retry. Log at ERROR with song, index and reason.
- Remove the `if path.exists():` guard that skipped missing segments.
- If a segment file vanishes between `ensure_segment` and `open` (evicted), retry once through `ensure_segment`. The playing song's segments ahead of the playhead are protected anyway (3.6).

### 3.5 Buffer-ahead policy (`playback.py`)

- Keep the Phase 0 fix: the window is relative to the playhead.
- `update_position` only re-requests segments when the playhead has entered a new segment since the last call. Position reports every 2 s then mostly do nothing.
- `seek`: bump epoch, then request from the new index (CRITICAL, 2× HIGH, NORMAL up to `SEGMENT_BUFFER_AHEAD_SEC`).
- `stop_playback`: no epoch bump needed. Lower-priority leftovers just drain. Optionally add `DownloadManager.drop_song(song_id)` to drop queued (not in-flight) items for a song that is no longer current.

### 3.6 `CacheStore`: real LRU, incremental accounting (F11)

- `touch(path)`: `os.utime(path)` when a segment is served, at most once per segment every 30 s (keep a small in-memory dict of last-touch times). With that, mtime equals last access, and sorting by mtime gives real LRU.
- Keep a running `total_bytes`: add on write, subtract on evict. Compute it in full only in `reconcile()` at startup.
- `maybe_evict()` after each write: O(1) when under the limit. Over the limit, scan once, sort by mtime, and evict to 80%, skipping protected segments:
  - the current song, `index >= current_index - SEGMENT_BEHIND`
  - its `init.bin`
  - `layout.json` files
  - any segment that is `IN_FLIGHT`
- On eviction, call `registry.evicted(key)` and delete the DB row.
- Drop the DB `last_accessed` updates (`_touch_segment`): mtime is the LRU source now. Keep the column for compatibility, or remove it together with the Phase 2 table recreation.

### 3.7 `/chunks` from memory

- `get_all_segment_statuses` maps `registry.snapshot(song_id)` to `pending|downloading|downloaded|error`. Map `QUEUED` and `MISSING` to `pending` and `IN_FLIGHT` to `downloading`. No filesystem calls.
- Registry is rebuilt from disk at startup by `reconcile()` (`DONE` for each file that matches `layout.json`).

### 3.8 Thread budget

- Request handlers block on `ensure_segment`, using Starlette's threadpool (40 by default). With 4 download workers plus the browser's 1–3 concurrent Range requests this is fine. Leave a comment in `serving.py` explaining why the handlers are sync (P21).

---

## 4. Tests to add

| Test | Asserts |
|---|---|
| `test_seek_requeues_queued_segment` | enqueue idx 5 (NORMAL, epoch 0); seek → request idx 5 (CRITICAL, epoch 1); worker processes it **once**, at CRITICAL order; no 2 s gap |
| `test_superseded_heap_item_skipped` | two heap items for one key: one download, one skip |
| `test_sync_and_worker_single_download` | mocked HTTP with 200 ms delay; `ensure_segment` and a worker started together → exactly **one** HTTP call, both see `DONE` |
| `test_sync_claims_queued_item` | key queued at NORMAL behind 20 others; `ensure_segment` returns as soon as its own fetch finishes (not after the queue drains) |
| `test_unique_tmp_names` | two concurrent `fetch_segment` calls for the same key (forced) never share a tmp path; final file is complete |
| `test_range_first_segment_failure_returns_json_error` | first segment fails → status 502 JSON, no `Content-Range` |
| `test_range_mid_stream_failure_raises` | second segment fails → generator raises; the response is not silently short |
| `test_lru_respects_access` | segments A (old, recently served) and B (new, never served); eviction removes B first |
| `test_eviction_updates_registry` | evicted key goes to `MISSING`; `/chunks` shows `pending` |
| `test_running_total_matches_scan` | after N writes and evictions, `total_bytes` == a full scan |
| `test_position_update_noop_within_segment` | 3 position reports inside one segment → `request()` called once |

Rewrite the existing `TestDownloadManager`, epoch and LRU tests against the new registry API. Don't keep tests for removed behaviour.

---

## 5. Acceptance criteria

- [ ] Unit suite green. The new modules each have a test file.
- [ ] Manual: play a song, seek to 75%, then back to 10%. No stall over 1 s on a cached region, and no "Too little data for declared Content-Length" (h11) error in `app.log`.
- [ ] Manual: set `CACHE_MAX_SIZE_MB=20`, play 6+ songs, replay the first one. Its recently played segments are still cached (LRU), and the current song never stalls because of eviction.
- [ ] `grep -n "time.sleep(0.05)\|_downloading\|_seg_status" -r backend/services` returns nothing.
- [ ] The public `StreamingService` methods used by `endpoints.py` keep the same signatures (or endpoints are updated in the same PR).

## 6. Risks and notes

- **This is the riskiest phase**: it rewrites concurrency code. Land 3.1–3.3 first, behind the existing endpoint API, with tests, then 3.4–3.7.
- **Starlette sync generators** run in the threadpool through `iterate_in_threadpool`. An exception raised there aborts the response, so check the behaviour with the TestClient test above and once in the real webview.
- **Keep the P14 checks** (206, `Content-Range`, byte count) in `fetch_segment` unchanged.
