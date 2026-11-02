# Cache & database

## Files on disk

`CacheStore` (`services/streaming/cache.py`) owns `cache/segments/` in the data directory:

```
cache/segments/
└── BAgTQhR8MLo/
    ├── layout.json     # cache identity + the segment table
    ├── init.bin        # ftyp + moov + sidx (absent for proportional layouts)
    ├── 0000.bin
    ├── 0001.bin
    └── …
```

Each file holds exactly the bytes of its range in the CDN file. `NNNN.*.tmp` files are in-progress
downloads; leftovers from a crash are removed at startup.

## Size accounting

The store keeps a per-file size map and a running total, filled by a full scan at startup
(`rescan()`) and updated on every write and delete. So checking the limit after a download is
O(1); the directory isn't scanned again.

## LRU eviction

The LRU clock is the file's **mtime**:

- set when the segment is downloaded;
- bumped by `touch()` each time the segment is served (at most once per 30 s per file, to limit
  filesystem writes).

`maybe_evict(protected)` runs after every successful download. When the total exceeds
`CACHE_MAX_SIZE_MB`, it sorts files by mtime and deletes the oldest until the total is at
**80 %** of the limit. It never deletes:

- the playing song's `init.bin`, and its segments from `current_index − SEGMENT_BEHIND` onwards;
- segments being downloaded (IN_FLIGHT);
- `layout.json`.

Each eviction removes the file and its DB row and sets the registry key back to MISSING, so the
segment bar and future requests see it as missing. Empty song directories are removed, except
that `layout.json` stays as long as the in-memory table refers to it.

## Startup reconciliation

`reconcile()` (called from `StreamingService.start()`) heals whatever a crash or a manual
deletion left behind, then rebuilds the in-memory state:

| Found | Action |
|---|---|
| song directory without `layout.json` | delete the directory and its rows (unknown layout) |
| `*.tmp` or unrecognised file | delete |
| file with no DB row | delete |
| DB row with no file | delete the row |
| file size ≠ row's `size_bytes`, or row's `layout_id` ≠ manifest | delete both |
| file matching its row and manifest | mark DONE in the registry |

After it, `/chunks` is answered from the registry with no filesystem calls.

## Database

One SQLite file (`userdb.sqlite`), SQLAlchemy 2, in `database/`. `session.py` sets **WAL mode**
and `busy_timeout=5000` (4 workers and the request handlers write concurrently), and provides
`session_scope()` (context manager) and `get_db()` (FastAPI dependency).

| Table | Key | Content |
|---|---|---|
| `segments` | `song_id` + `index` (−1 = init) | `byte_start`, `byte_end`, `size_bytes`, `duration_ms`, `status`, `file_path`, `layout_id` |
| `songs` | `id` | cached metadata: title, artist, album, duration, thumbnail |
| `playlists` | `id` | name, owner, thumbnail, song count |
| `playlist_songs` | auto id | playlist ↔ song with position |
| `liked_songs` | `song_id` | liked-songs cache |

The `segments` table is only a cache: if `init_db()` finds it missing a column, it drops and
recreates it, and reconciliation then removes the now-orphaned files. Its `last_accessed` column
is no longer written (the LRU uses file mtimes).

There is no playback state in the database: the playback session is in memory, and the queue
belongs to the frontend.

## In-memory caches

| Cache | Where | Bound |
|---|---|---|
| extracted streams, extraction failures | `StreamExtractor` | `BoundedDict(256)` each |
| stream info (segment tables) | `StreamingService._stream_info_cache` | `BoundedDict(256)` |
| last error code per song | `StreamingService._stream_errors` | `BoundedDict(256)` |
| segment states | `SegmentRegistry` | one entry per known segment |

## Known limitation

After a restart, a cached song still needs one extraction (~1 s) before it plays: the segment
table is rebuilt from the stream URL, not from `layout.json`. Serving cached songs straight from
`layout.json` is an open item in `AGENTS.md`.
