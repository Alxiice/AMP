# AMP v2 — Design Document (Tauri web frontend, DASH-segment streaming)

> **Purpose**: Authoritative spec for AMP v2. An agent reading only this document should be able to build the project. Where v1 was exploratory, this version is prescriptive: decisions are made, alternatives are named only where they remain open.

> **Status (2026-10-31)**: Phases 1–5 below are implemented; refactoring Phase 0 of [improvement-plan/](improvement-plan/README.md) is done (AGENTS.md Revisions 7–8). Where the current code still differs from this spec, the section says so in a **Current state** note and names the improvement-plan phase that closes the gap. Progress: [AGENTS.md](AGENTS.md).

> **Scope note**: Personal prototype. Not for distribution. Cookie-based YouTube extraction is against YouTube's ToS; accepted risk for this project. External tools (yt-dlp, Node.js) are allowed to break; tests pin two known-good video IDs and will be updated if they break.

---

## 1. Goals

| # | Goal | Target |
|---|---|---|
| G1 | Time to first audio after pressing play | < 300 ms (init + first segment only) |
| G2 | Seamless playback | Pre-buffer ahead of playhead; zero stalls on decent connection |
| G3 | Instant seek | Local endpoint serves cached bytes with real HTTP Range support |
| G4 | Persistent cache | Segments survive restarts; LRU eviction at 500 MB |
| G5 | Native desktop app | Tauri shell, web UI, no browser required |

**Non-goals**: multi-user, cloud sync, offline downloads-as-files, lyrics, social features, mobile.

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Tauri App (React + TypeScript + Vite)                   │
│  ┌────────────┐ ┌──────────┐ ┌────────────────────────┐  │
│  │  PlayerBar │ │  Search  │ │  Library / Liked / ... │  │
│  └────────────┘ └──────────┘ └────────────────────────┘  │
│  HTMLAudioElement ←── HTTP Range ──┐                     │
│  ApiClient (fetch, Bearer token)   │                     │
│  BackendSidecar (spawn + health)   │                     │
└────────────────────────────┬───────┴─────────────────────┘
                             │ HTTP, 127.0.0.1:8000, Bearer token
┌────────────────────────────▼─────────────────────────────┐
│  FastAPI Backend (Python, sidecar process)               │
│  ┌────────────┐ ┌──────────────┐ ┌────────────────────┐  │
│  │ AuthRoutes │ │  Endpoints   │ │  Logs / Health     │  │
│  └────────────┘ └──────────────┘ └────────────────────┘  │
│  Services (thread-safe singletons)                       │
│  ├── AuthService      → cookies, SAPISIDHASH, ytmusicapi │
│  ├── YouTubeService   → search, metadata, likes         │
│  └── StreamingService → DASH segments, cache, playback  │
│      ├── SegmentFetcher (yt-dlp → manifest URL)         │
│      ├── ManifestParser (MPD → segment table)           │
│      ├── DownloadManager (4 workers, priority queue)    │
│      └── PlaybackSession (in-memory, epoch-based)       │
└────────────────────────────┬─────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────┐
│  SQLite (userdb.sqlite) + filesystem cache               │
│  .amp/cache/segments/{song_id}/init.bin, 0000.bin, ...   │
└──────────────────────────────────────────────────────────┘
                             ▼
                   YouTube Music / googlevideo.com / yt-dlp
```

**Data flow (play)**: UI `play(song_id)` → `POST /api/stream/{id}/play` → queue init + segment 0 as CRITICAL → UI sets `audio.src = /api/stream/{id}/audio` → endpoint serves init+segments from cache, downloading missing ones synchronously → browser plays, issues its own Range requests as it buffers → DownloadManager pre-fetches ahead of the playhead.

---

## 3. Stack

| Layer | Technology |
|---|---|
| Shell | Tauri v2 (Rust core, system webview) |
| Frontend | React 18 + TypeScript + Vite |
| Audio | `HTMLAudioElement` (MSE is an optional Phase-4 upgrade, §8.4) |
| Backend | FastAPI + Uvicorn |
| ORM / DB | SQLAlchemy 2.x + SQLite (WAL mode, single `userdb.sqlite`) |
| Config | `pydantic-settings` + `.env` |
| YouTube metadata | `ytmusicapi` (cookie auth) |
| Stream URLs | `yt-dlp[default]` Python API (pulls in `yt-dlp-ejs`, the JS challenge solver), `js_runtimes={"node": {}}` |
| HTTP | `requests` (CDN range downloads) |
| Packaging | PyInstaller (backend sidecar binary) + `tauri build` |
| Dependencies | `requirements.txt` (major-version caps, yt-dlp uncapped) → `requirements.lock` (exact pins, used by CI) |
| Tests | pytest (unit, mocked) + pytest integration (pinned songs) + pytest-cov |
| Lint / CI | Ruff (`.ruff.toml`); GitHub Actions: Python CI (lint + unit tests + coverage → Codecov), Tauri Build (sidecar + `.deb`) |
| External req. | Node.js on `PATH` (yt-dlp JS challenges), Python 3.13 (3.10+ supported), Rust toolchain (Tauri builds) |

**Format choice**: default stream format **itag 140 (AAC 128 kbps, MP4)** — plays in every webview (Chrome/WebView2, WKWebKit, WebKitGTK). Itag 251 (Opus/WebM, ~160 kbps) is supported as a config option; prefer 140 unless Opus is verified on the target platform. Both are DASH on YouTube; both concatenate init+segments into a valid file.

---

## 4. Directory Structure

```
(repo root)
├── README.md                   # logo, CI badges, quick start, doc index
├── DESIGN_DOC_2.md / AGENTS.md # spec / progress tracker
├── improvement-plan/           # refactoring phases 0–6
├── icon/                       # logo-square.svg, logo-round.svg
├── .github/workflows/          # python-ci.yml, tauri-build.yml
├── .ruff.toml
└── amp/                        # the application (below)

amp/
├── backend/
│   ├── main.py                 # entry: argparse + uvicorn
│   ├── config.py               # pydantic-settings, creates dirs on import
│   ├── api/
│   │   ├── server.py           # FastAPI app, CORS, token auth, DB init
│   │   ├── endpoints.py        # library + streaming + logs routes
│   │   └── auth_routes.py      # 6 auth endpoints
│   ├── services/
│   │   ├── auth.py             # AuthService, CredentialStore, SAPISIDHASH
│   │   ├── youtube.py          # YouTubeService (ytmusicapi wrapper)
│   │   └── streaming.py        # StreamingService + DownloadManager + parser
│   ├── database/
│   │   ├── models.py           # Song, Playlist, PlaylistSong, LikedSong, Segment
│   │   └── session.py          # engine (WAL), session factory, init
│   ├── utils/
│   │   ├── logger.py           # app.log + streaming.log + in-memory ring
│   │   └── dash.py             # MPD parsing (pure functions, unit-testable)
│   └── tests/                  # unit tests (mocked) + integration tests
├── frontend/
│   ├── src/
│   │   ├── api.ts              # typed fetch wrapper, token header
│   │   ├── sidecar.ts          # spawn/kill backend, health poll
│   │   ├── components/         # PlayerBar, SegmentBar, SongList, ...
│   │   ├── pages/              # Search, Library, Playlists, Auth, Logs
│   │   └── state.ts            # queue + playback state (frontend-owned)
│   ├── public/                 # favicons + site.webmanifest (AMP logo)
│   ├── index.html              # CSP meta, favicon links
│   ├── vite.config.ts
│   ├── src-tauri/              # tauri.conf.json (sidecar, capabilities), icons/, Cargo.lock
│   │   └── binaries/           # amp-backend-<target-triple> (PyInstaller output, gitignored)
│   └── package.json
├── .amp/                       # runtime: cache/, logs/ (gitignored)
├── amp-backend.spec            # PyInstaller spec for the sidecar
├── pyproject.toml              # deps + pytest + coverage config
├── requirements.txt / requirements.lock
└── README.md
```

---

## 5. Backend

### 5.1 Configuration (`config.py`)

| Setting | Default | Notes |
|---|---|---|
| `HOST` | `127.0.0.1` | **Never `0.0.0.0` in v2** |
| `PORT` | `8000` | |
| `AUTH_TOKEN` | `None` (CLI arg `--token`) | Optional. When set, every request needs `Authorization: Bearer <token>`; when unset the API is open (Host check still enforced) |
| `DEBUG` | `False` | |
| `CACHE_DIR` / `SEGMENTS_DIR` / `LOGS_DIR` | `.amp/cache`, `.amp/cache/segments`, `.amp/logs` | created on import |
| `DB_PATH` | `userdb.sqlite` | single DB (playdb dropped — playback state is in-memory) |
| `CACHE_MAX_SIZE_MB` | `500` | evict down to 80% when exceeded |
| `SEGMENT_BUFFER_AHEAD_SEC` | `30` | how far ahead to pre-fetch |
| `SEGMENT_BEHIND` | `2` | segments kept behind playhead for seek-back |
| `STREAM_FORMAT` | `140` | itag; 251 allowed |
| `YTDLP_PLAYER_CLIENTS` | `["visionos", "default"]` | yt-dlp player clients tried in order; `default` = yt-dlp's choice (§6.2) |
| `DOWNLOAD_WORKERS` | `4` | |
| `HTTP_TIMEOUT_CONNECT_S` / `HTTP_TIMEOUT_READ_S` | `5` / `30` | |
| `MAX_RETRIES` | `3` | backoff 0.5 / 1 / 2 s + jitter |

Computed paths (cache, segments, logs, DB file) are private attributes set by `Settings.configure_paths(data_dir=None, db_file=None)`, which `model_post_init` calls with the defaults above. Tests and the future `--data-dir` option (improvement-plan Phase 6) call it to redirect storage; `snapshot_paths()` / `restore_paths()` undo the change. Never monkeypatch the private attributes (§10 P27).

### 5.2 Server (`api/server.py`)

1. Create FastAPI app.
2. **Auth middleware**: every request except `GET /` and `GET /api/health` must carry a `Host` of `127.0.0.1`/`localhost` (DNS-rebinding guard), and — when `AUTH_TOKEN` is configured — `Authorization: Bearer <token>`. Reject otherwise (401/403). Open mode (no token) is the default; cross-site POST protection in open mode is improvement-plan Phase 5 (F15).
3. **CORS**: explicit origins only — `tauri://localhost`, `http://tauri.localhost`, and the Vite dev origin. Never `*` with credentials.
4. CORS preflight must not require the token (middleware exempts `OPTIONS`).
5. Init DB, mount routers, startup/shutdown hooks (start DownloadManager, reconcile cache, shutdown executor).
6. **Blocking I/O rule**: any handler that calls `requests`, yt-dlp, or does file I/O is a plain `def` (FastAPI runs it in the threadpool). Never `async def` for those.
7. **Startup check**: log whether `node` is on `PATH` and `yt_dlp_ejs` is importable (WARNING if either is missing — extraction will degrade).

### 5.3 Services — thread-safe singletons

```python
_instance: Optional[Service] = None
_lock = threading.Lock()

def get_service() -> Service:
    global _instance
    with _lock:                      # v1 had a race here
        if _instance is None:
            _instance = Service(...)
        return _instance
```

Never construct services directly. All shared state (cookies, segment tables, playback session) lives in the singletons.

### 5.4 Auth (`services/auth.py`)

- Cookie-based auth only (OAuth is dead for YTMusic as of 2025). Optional: search and playback work signed out.
- **Only youtube.com cookies are stored.** `filter_youtube_cookies(jar)` keeps a cookie only if its domain (leading dot stripped) is `youtube.com` or ends with `.youtube.com`; for duplicate names, `.youtube.com` wins over subdomains. Browser import reads the local cookie store with `yt_dlp.cookies.extract_cookies_from_browser()` (no network request).
- **Session expiry** is decided only by ytmusicapi 401/403 (`youtube.py`) and `status(verify=True)`. A googlevideo CDN 403 means the signed stream URL expired, not the session (§6.5).
- `SAPISIDHASH = SHA1(ts + " " + __Secure-3PAPISID + " " + "https://music.youtube.com")`.
- `CredentialStore`: `.amp/cache/ytm_session.json`, atomic write (tmp + `os.replace`), `0600`.
- Lazy `YTMusic` client construction (offline launch must not look like a failed login).
- `get_cookie_header()` feeds both ytmusicapi headers and CDN requests.
- States: `signed_out → signed_in → expired`.

### 5.5 YouTubeService (`services/youtube.py`) — unchanged from v1

Wraps `ytmusicapi`: search, song/artist/album/playlist metadata, liked songs, user playlists. Dataclasses + `to_dict()`. Authenticated calls go through `AuthService.client` (falls back to anonymous for search/metadata).

---

## 6. Streaming Core (DASH segments)

This section replaces v1 §9. The unit of caching is now the **segment**, taken from YouTube's own DASH manifest, not a proportionally-computed byte range.

### 6.1 Concepts

A YouTube audio stream URL (from yt-dlp) resolves to one of two things:

- **DASH manifest** (XML, `<MPD>`): describes an **initialization segment** (file header: ftyp/moov or EBML/Tracks) and an ordered list of **media segments**, each an exact byte range of the same resource, each with an exact duration. `init + segments` concatenated = a valid, playable audio file.
- **Progressive file** (binary): one continuous file; Range requests work, but segment boundaries are unknown → fall back to v1-style proportional chunking (§6.5).

### 6.2 Getting the manifest URL

```python
def build_ydl_opts(player_client, fmt, cookie_file):
    opts = {
        "quiet": True, "no_warnings": True, "skip_download": True, "socket_timeout": 15,
        "js_runtimes": {"node": {}},                     # top-level dict, §10 P2
    }
    if player_client:                                    # None = yt-dlp's default client
        opts["extractor_args"] = {"youtube": {"player_client": [player_client]}}  # dict of lists
    if fmt:
        opts["format"] = fmt                             # e.g. "bestaudio/best"
    if cookie_file:
        opts["cookiefile"] = cookie_file                 # Netscape temp file, 0600, deleted in finally (P23)
    return opts

for client in settings.YTDLP_PLAYER_CLIENTS:          # "default" = yt-dlp's own choice
    opts = build_ydl_opts(client, "bestaudio/best", cookie_file_if_client_supports_cookies)
    opts["ignore_no_formats_error"] = True             # warn, don't raise; we choose in Python
    info = YoutubeDL(opts).extract_info(f"https://www.youtube.com/watch?v={song_id}", download=False)
    stream = select_audio_format(info)   # itag STREAM_FORMAT > m4a audio-only > any audio-only; never muxed video
    if stream: break                     # "Video unavailable"/"Private video" stops the rotation
wait_until(stream.available_at)          # §10 P26, capped at 30 s
```

Extraction lives in `services/extractor.py` (`StreamExtractor`), which returns an `ExtractedStream`: URL, itag, ext, MIME type, codec, file size (`filesize` or the URL's `clen=`), duration (`info["duration"]`), title, and expiry (the URL's `expire=` minus 5 min). It has no FastAPI imports and no knowledge of segments.

- Use `www.youtube.com` watch URLs: `music.youtube.com` triggers "The page needs to be reloaded" more often.
- **Client order** is the `YTDLP_PLAYER_CLIENTS` setting, default `["visionos", "default"]`, one extraction per client (at most 2, not 24). Measured 2026-10-31 (yt-dlp 2026.10.26): `visionos` returns itag 140 with no `available_at` delay (~1 s), but yt-dlp drops it when cookies are passed, so it runs anonymously. `default` (tv_samsung) returns itag 140 after a ~5 s delay and uses cookies when signed in. `web`, `web_music`, `web_safari`, `tv`, `ios`, `mweb`, `android_vr` returned no audio-only formats; `android` without a PO token returns only muxed itag 18 (§10 P26).
- **Single flight**: concurrent callers for a song share one extraction, and one stream-info build. Failures are negative-cached (5 min, 30 min for `unavailable`). A 403 refresh passes the URL that failed, so N workers cause one re-extraction.
- `/api/health` reports `services.extractor: {node, ejs, yt_dlp}`. Without `node`, extraction fails at once with `node_missing`.
- No TLS shortcuts: `nocheckcertificate` is never set.

Fetch the URL with CDN headers (cookie when signed in, §10 P1). If the body starts with `<?xml` or `<MPD` → DASH path. Otherwise → progressive path, segmented from the extracted size and duration (HEAD / `Range: bytes=0-0` probe only when the size is unknown). The extracted stream is cached until its URL expires; refresh on 403 (§6.5).

> **Current state**: yt-dlp returns direct googlevideo URLs, never MPD manifests, so the DASH path never runs and every song goes through the progressive fallback (F4). Phase 1 gave the progressive path real durations and sizes; Phase 2 adds a real segment table.

### 6.3 Manifest parsing (`utils/dash.py`)

Pure functions, fully unit-testable with fixture XML. Handle namespace `urn:mpeg:dash:schema:mpd:2011`.

Extract from the audio `Representation`:

- `BaseURL`
- Init segment: byte range from `SegmentList/Initialization@sourceURL` or `SegmentTemplate@initialization` + `@indexRange` (resolve `$RepresentationID$`, `$Bandwidth$`, `$Ext$` tokens).
- Media segments, **two supported forms**:
  - **SegmentList** (what YouTube audio manifests use): `SegmentURL@mediaRange="start-end"` per segment → exact byte ranges.
  - **SegmentTemplate + SegmentTimeline**: `S@t/d/r` entries → durations; byte ranges from `mediaRange` if present, otherwise numbered segment URLs (`$Number$` token) downloaded as individual files.

Output — the **segment table**, cached per song:

```python
@dataclass
class SegmentInfo:
    index: int            # 0..N-1 (init is index -1, stored separately)
    byte_start: int
    byte_end: int         # inclusive
    duration_ms: int
    url: str              # resource URL (range appended via header)

@dataclass
class StreamInfo:
    song_id: str
    title: str
    duration_ms: int
    mime_type: str        # audio/mp4 or audio/webm
    init_range: tuple[int, int]
    segments: list[SegmentInfo]
    total_bytes: int      # exact: init + sum(segment sizes)
    is_dash: bool         # False → progressive fallback
```

### 6.4 Progressive fallback (non-DASH URLs)

Keep v1 logic, reduced: size via `clen=` param → HEAD → `Range: bytes=0-0` probe (3 strategies, drop the yt-dlp and bitrate-estimate fallbacks — if all three fail, the song is unplayable, report an error). Segments = proportional byte ranges of `duration_ms / SEGMENT_TARGET_SEC` (default 5 s — smaller than v1's 10 s for faster first audio). Marked `is_dash=False`; everything downstream is identical.

### 6.5 Segment download pipeline

`download_segment(song_id, index)` — the robustness-critical path:

1. **Dedupe**: skip if status is DOWNLOADED or already in `_downloading` (per-song set, lock-protected).
2. **HTTP GET** with `Range: bytes=start-end` and CDN headers (`Cookie` from AuthService — without it, 403, §10 P1). Timeouts from config.
3. **Verify the response**: status must be **206**, `Content-Range` must match the requested range, and received byte count must equal `byte_end - byte_start + 1`. A 200 (range ignored) or short read = failure; never write the file.
4. **Atomic write**: write to `{index:04d}.bin.tmp`, `os.replace()` to final name. A crash mid-download can never leave a corrupt segment that looks complete.
5. **Record**: insert/update `segments` DB row (status, size, `last_accessed`), update in-memory status.
6. **Retry**: up to `MAX_RETRIES` with backoff 0.5/1/2 s + jitter, re-queued at same priority. Distinguish:
   - **403** → refresh stream URL once (clear song caches, re-extract, rebuild segment table — byte layout may change), then retry. Other 4xx → ERROR, no retry. A CDN 403 **does not touch auth state**: the refresh still extracts with the user's cookies (§5.4).
   - **429 / 5xx / timeout** → backoff and re-queue (transient).
7. After every successful download, run `cleanup_cache()` (cheap check) and update `last_accessed`.

Files: `.amp/cache/segments/{song_id}/init.bin` and `{index:04d}.bin`.

### 6.6 Cache & LRU

- Metadata in `segments` table: `song_id, index, byte_start, byte_end, size_bytes, duration_ms, status, file_path, last_accessed` (PK: `song_id, index`).
- `cleanup_cache()`: sum file sizes; if over `CACHE_MAX_SIZE_MB`, evict by `last_accessed ASC` until ≤ 80% of max. Delete file + DB row. Never evict segments of the currently-playing song ahead of the playhead.
- **Startup reconciliation**: scan `SEGMENTS_DIR`; delete orphan files (no DB row), delete rows with missing files, verify file sizes match `size_bytes` (mismatch → delete both). This heals any crash damage.
- In-memory caches (`_stream_info`, `_stream_urls`, `_segment_tables`) are **bounded**: `functools.lru_cache(maxsize=256)` or a dict with a size cap. v1 leaked these.

### 6.7 Local audio endpoint — real Range support

`GET /api/stream/{song_id}/audio` — this is what the browser's `<audio>` element talks to. **It must implement `Range` correctly** (v1 advertised `Accept-Ranges` but ignored the header — with a browser frontend that bug breaks seeking).

Virtual byte layout: `[init][segment 0][segment 1]...[segment N-1]`. All offsets exact from the segment table.

| Request | Behavior |
|---|---|
| No `Range` header | `200`, full stream, `Content-Length: total_bytes`, `Accept-Ranges: bytes` |
| `Range: bytes=a-b` | `206`, `Content-Range: bytes a-b/total`, `Content-Length: b-a+1` |
| `Range: bytes=a-` | `206`, from `a` to end |
| Unsatisfiable | `416` with `Content-Range: bytes */total` |

Serving: map the requested byte window to segment files (a window can span two segments — read across the boundary), reading only the needed byte ranges from disk. **Missing segment → download it synchronously before responding** (this is the G1 path: first request waits ~200 ms for init+segment 0). Content-Type from `StreamInfo.mime_type`. `Cache-Control: no-cache`.

### 6.8 Buffer-ahead & priorities

On `POST /api/stream/{song_id}/play` (or first audio request):

- Queue **init** and the **segment at the playhead** at CRITICAL.
- Queue next 2 segments HIGH, then NORMAL until `SEGMENT_BUFFER_AHEAD_SEC` (30 s) of audio **ahead of the playhead** is covered. The window is measured from the playhead segment, not from the song start (accumulate `duration_ms` from the start index, O(n)).
- Keep `SEGMENT_BEHIND` (2) segments behind the playhead cached (don't evict).
- `DownloadManager`: `PriorityQueue` + `ThreadPoolExecutor(4)`, daemon threads, started at app startup, shut down on app shutdown.

### 6.9 Seek — epoch-based cancellation

`seek_to_position(position_ms)`:

1. Bump the song's **epoch** (monotonic counter). Workers check the epoch before writing a segment; a stale worker (old epoch) discards its result and does not update status.
2. Map `position_ms → segment index` via the segment table (exact durations in DASH mode).
3. Re-queue from the new position with buffer-ahead priorities.

This fixes v1's race where an in-flight download for a pre-seek position completed and overwrote status with stale data.

### 6.10 PlaybackSession (in-memory)

`PlaybackInfo`: `song_id, current_segment_index, position_ms, is_playing, volume, epoch, last_updated`. `position_ms` is reported by the frontend every 2 s (`POST /api/stream/position`) and drives buffer-ahead. Not persisted — playback state is frontend-owned.

---

## 7. API Specification

All under `/api`. When a token is configured, all require it except `GET /` and `GET /api/health` (§5.2). All blocking handlers are plain `def`. Additional endpoints implemented since this table was written: `GET /api/stream/cache-info`, `POST /api/auth/tauri-cookies` and the sign-in flow routes (consolidated in improvement-plan Phase 5).

**Rule**: declare specific routes (`/stream/logs`, `/stream/playback-state`) **before** parameterized ones (`/stream/{song_id}`).

| Method | Endpoint | Response |
|---|---|---|
| GET | `/` , `/api/health` | app info / `{status, services}` |
| GET | `/api/search?q=&type=&limit=` | `SongResponse[]` |
| GET | `/api/song/{id}` | `SongResponse` |
| GET | `/api/artist/{id}` , `/api/album/{id}` , `/api/playlist/{id}` | metadata dicts |
| GET | `/api/user/playlists` | user playlists (auth) |
| GET | `/api/user/likes` | liked songs (auth) |
| GET | `/api/stream/info/{id}` | `StreamInfo` (segment table summary) |
| GET | `/api/stream/{id}/audio` | **binary, full Range support (§6.7)** |
| GET | `/api/stream/{id}/chunks` | segment status list (for visualization) |
| POST | `/api/stream/{id}/play` | start session + buffer |
| POST | `/api/stream/pause` , `/resume` , `/stop` | `{message}` |
| POST | `/api/stream/position?position_ms=` | update playhead |
| POST | `/api/stream/seek?position_ms=` | seek + re-buffer (§6.9) |
| POST | `/api/stream/buffer/{id}` | force buffer-ahead |
| GET | `/api/stream/playback-state` | `PlaybackInfo` |
| GET | `/api/stream/logs` | recent streaming log lines |
| GET | `/api/auth/status?verify=` | `{state, is_authenticated, account}` |
| POST | `/api/auth/cookies` , `/cookie-header` , `/import-browser` , `/open-signin` , `/logout` | auth flow |
| GET/POST/DELETE | `/api/logs` | frontend log relay (last 500) |

Response shapes are consumed directly by the TypeScript client (`frontend/src/api.ts` defines the types). No v1-style bridge normalization layer — the frontend adapts.

**Dropped from v1**: queue endpoints, `playdb`, legacy `/api/playback/*` (frontend owns the queue), dashboard HTML (logs endpoints suffice; a simple Logs page in the app replaces it).

---

## 8. Frontend (Tauri + React)

### 8.1 Lifecycle

- `sidecar.ts` spawns the backend: in dev, `venv` Python `-m backend.main`; in prod, the PyInstaller binary registered as a Tauri sidecar (`tauri.conf.json → bundle.externalBin`, file `src-tauri/binaries/amp-backend-<target-triple>`). Sidecar spawning comes from `tauri-plugin-shell` (Tauri v2 has no `shell-sidecar` cargo feature).
- Optional token: when used, `crypto.randomUUID()` per launch, passed as `--token` and attached to every fetch as `Authorization: Bearer`. The current frontend runs in open mode (no token).
- Health poll every 1 s; UI shows backend status; manual restart button.
- Backend stdout/stderr captured to an in-memory ring (shown in Logs page), with **separate handlers** for stdout/stderr (§10 P6).

> **Current state**: the Tauri shell plugin's `encoding` spawn option broke spawning and was removed, so P7 (UTF-8 decoding of sidecar output on Windows) is not handled in the frontend. Spawn scoping, kill-on-exit and the PyInstaller data dir are improvement-plan Phase 6 (F14, F16).

### 8.2 Pages / components

| Component | Purpose |
|---|---|
| `PlayerBar` (persistent) | play/pause/stop, seek slider, time, volume, thumbnail/title |
| `SegmentBar` | one cell per segment, colored by status (cached/downloading/queued/error), click-to-seek; polled at 500 ms **with an in-flight guard** (§10 P12) |
| `Search` | query box, results list, play per result |
| `Library` | liked songs list |
| `Playlists` | user playlists + tracks |
| `Auth` | import-from-browser buttons, sign-in, status, logout |
| `Logs` | backend stdout, streaming logs, API log relay |

Queue state (list of songs, current index, next/previous) is **frontend-owned** in `state.ts` — no backend queue API.

### 8.3 Player

```ts
const audio = new Audio(`http://127.0.0.1:8000/api/stream/${songId}/audio`);
```

- The browser issues Range requests natively; the backend (§6.7) makes seeks instant once segments are cached.
- `audio.currentTime` → seek slider; slider release → `audio.currentTime = t` + `POST /api/stream/seek`.
- Position reported to backend every 2 s (drives buffer-ahead).
- `onended` → next in queue.

### 8.4 Optional upgrade: MSE

If `<audio>` proves insufficient (gapless transitions, adaptive quality), replace the audio element with **Media Source Extensions**: append init + segments to a `SourceBuffer` as they download. Works best with itag 140 (fMP4). This is a Phase-4 option, not a requirement.

### 8.5 Webview security

CSP in `index.html`:

```
default-src 'self';
connect-src 'self' http://127.0.0.1:8000;
media-src 'self' http://127.0.0.1:8000;
img-src 'self' https://i.ytimg.com https://*.ggpht.com https://lh3.googleusercontent.com data:;
style-src 'self' 'unsafe-inline';
```

The same policy is set in `tauri.conf.json → app.security.csp`. `media-src` is required for `<audio>` to load from the backend; `lh3.googleusercontent.com` serves YouTube Music thumbnails. Favicons and the web manifest are same-origin (`frontend/public/`), covered by `default-src 'self'`.

Tauri v2 capabilities: no shell/fs plugins needed beyond sidecar spawn.

### 8.6 Branding

The AMP logo lives in `icon/` (repo root): `logo-square.svg` (squircle, used for the app and README) and `logo-round.svg`. Web favicons in `frontend/public/` come from the same artwork. Tauri bundle icons in `src-tauri/icons/` are generated from `logo-square.svg` with `npx tauri icon ../../icon/logo-square.svg -o <dir>`; the desktop sizes listed in `tauri.conf.json → bundle.icon` are committed.

---

## 9. Database

Single SQLite (`userdb.sqlite`), WAL mode, `busy_timeout=5000` (4 download workers + request handlers share the engine).

| Table | Key columns | Purpose |
|---|---|---|
| `songs` | `id` PK, `title`, `artist`, `album`, `duration_ms`, `thumbnail_url`, `updated_at` | cached metadata |
| `playlists` | `id` PK, `name`, `owner`, `thumbnail_url`, `song_count` | playlists |
| `playlist_songs` | `playlist_id`+`song_id`+`position` PK | playlist tracks |
| `liked_songs` | `song_id` PK, `liked_at` | liked-songs cache |
| `segments` | `song_id`+`index` PK, `byte_start`, `byte_end`, `size_bytes`, `duration_ms`, `status`, `file_path`, `last_accessed` | segment cache metadata |

Always close sessions (`try/finally` or FastAPI dependency). `echo=DEBUG`.

---

## 10. Pitfalls (canonical list — do not re-learn these)

Carried from v1, still binding:

- **P1 — CDN requires the Cookie header.** Every googlevideo.com request (segment download, size probe) must include `Cookie` from AuthService. Missing it = 403 on everything.
- **P2 — yt-dlp needs a JS runtime and solver.** Pass `js_runtimes={"node": {}}` as a **top-level** option (CLI: `--js-runtimes node`) and install `yt-dlp[default]` so `yt-dlp-ejs` is present. Node.js is a hard dependency. (The old `extractor_args={"youtube": ["js_runtimes=node"]}` form was silently ignored, §10 P25.)
- **P3 — Cache expensive lookups.** yt-dlp extraction and stream info are cached per song (bounded, §6.6). First call ~2 s, then instant.
- **P4 — Stream URLs expire (~6 h).** On 403: refresh URL, rebuild segment table, retry once.
- **P5 — Never trust one Content-Length strategy** (progressive fallback only): `clen=` param → HEAD → `Range: bytes=0-0` probe.
- **P6 — Subprocess pipe deadlock.** Separate reader threads for stdout/stderr; never read both sequentially from one thread.
- **P7 — Windows encoding.** `encoding="utf-8", errors="replace"` on subprocess pipes (Python side: decode bytes explicitly, as `amp_control.py` does). *Not currently handled in the Tauri frontend* — see §8.1.
- **P9 — FastAPI route order.** Specific routes before parameterized (`/stream/logs` before `/stream/{song_id}`).
- **P11 — localStorage is origin-scoped.** Cross-port sharing needs the server-side relay (`POST /api/logs` → `GET /api/logs`). (Kept for reference; v2's UI is same-app, but the relay stays.)
- **P12 — Overlapping polls.** Guard every polling timer with an in-flight flag.

New in v2 (from the v1 review):

- **P13 — `song_id` is a path parameter.** Validate against `^[A-Za-z0-9_-]{11}$` before using it in file paths. Path traversal otherwise.
- **P14 — Verify 206 + Content-Range + byte count.** A range-ignoring 200 saved as a segment silently corrupts the cache.
- **P15 — Atomic writes only.** tmp file + `os.replace()`. A crash must never leave a partial segment that looks complete.
- **P16 — Implement Range for real.** The browser's `<audio>` seeks via Range. Advertising `Accept-Ranges` without honoring the header breaks seeking.
- **P17 — Bind `127.0.0.1`, require the token, validate `Host`.** The API reads the user's YouTube session (liked songs) and controls playback. v1's `0.0.0.0` + `CORS *` + no auth let any LAN peer or any open webpage drive it.
- **P18 — Seek needs an epoch.** Bump a per-song epoch on seek; stale in-flight downloads discard their results.
- **P19 — Bound in-memory caches.** v1's `_stream_info_cache` etc. grew forever. Use `lru_cache` or a capped dict.
- **P20 — SQLite WAL + busy_timeout.** Concurrent workers + handlers will hit `database is locked` otherwise.
- **P21 — Blocking I/O in `async def` freezes the event loop.** Handlers doing HTTP/yt-dlp/file I/O are plain `def`.
- **P22 — Webview codec support.** Default itag 140 (AAC/MP4). Verify Opus/WebM on the target platform before switching to 251.
- **P23 — yt-dlp cookie temp file.** Netscape cookie file must be `0600` and deleted in a `finally` — it contains the user's full Google session.
- **P24 — Never log full CDN URLs or the Cookie header** (they contain auth signatures).

New from refactoring Phase 0 (AGENTS.md Revision 7):

- **P25 — yt-dlp ignores malformed options silently.** `extractor_args` must be `{extractor: {key: [values]}}`; a plain list is dropped with no warning, so `player_client` / `po_token` never applied. Build options through `build_ydl_opts()` and keep `test_ydl_opts_player_client_applied`, which checks the value yt-dlp actually sees.
- **P26 — Stream URLs can 403 for a few seconds after extraction.** Some clients (TVHTML5, yt-dlp's default when a JS runtime is available) return formats with `available_at`; requests before that time get 403. Sleep until `available_at` (capped). Relatedly, `android` without a PO token offers only muxed itag 18 — don't put it first.
- **P27 — Don't monkeypatch pydantic private attributes.** With pydantic 2.14, `monkeypatch.undo()` deletes `settings._cache_dir` instead of restoring it, breaking every later test. Use `Settings.configure_paths()` / `restore_paths()` (§5.1).
- **P28 — Cookie imports must be domain-filtered.** A browser cookie jar holds every site's session. Keep only youtube.com cookies (§5.4).

---

## 11. Testing

- **Unit** (`pytest -m "not integration"`, fully mocked, no network): config, models, `dash.py` manifest parser (fixture MPDs: SegmentList form, SegmentTemplate+Timeline form, init range variants), segment byte-range math, Range-header mapping (§6.7), auth (SAPISIDHASH, CredentialStore), DownloadManager priority/dedupe/epoch, endpoints (TestClient).
- **Integration** (`pytest -m integration`, network, ~2 min, cookies optional): `test_integration.py` pins `dQw4w9WgXcQ` (Rick Astley) and `LTDxBgP0lqA` (The Weeknd — Blinding Lights); `test_integration_download.py` downloads every segment of `BAgTQhR8MLo` (override with `AMP_TEST_SONG_ID`, e.g. `Tmz3mpOq8aE`). Both must handle streams without an init segment (`has_init=False`). If a pinned song breaks (removed/region-blocked), update the ID — accepted per scope. Run after every yt-dlp upgrade.
  - manifest fetch + parse end-to-end
  - init + first 3 segments download, sizes verified
  - full audio endpoint: `Range: bytes=0-1023` returns 206 with correct bytes; seek to 50% serves correct segment
  - cache eviction and startup reconciliation with a temp cache dir
- Singletons reset between tests (`conftest.py` clears `_instance` globals); temp dirs for cache/DB via the `temp_dirs` fixture (`configure_paths` / `restore_paths`, §10 P27); integration tests copy cookies to `ytm_session.json` and clean up.
- **Lint**: `ruff check amp/backend/` with `.ruff.toml` (pyflakes, pycodestyle errors, bugbear, bandit; tests excluded). Inline `noqa` must give a reason.
- **Coverage**: `pytest -m "not integration" --cov=backend` (config in `amp/pyproject.toml`, tests omitted, branch coverage). `fail_under = 60` is a regression floor; raise it as coverage grows.
- **CI** (GitHub Actions, every push and PR): *Python CI* installs `requirements.lock`, runs Ruff, unit tests with coverage, uploads to Codecov. *Tauri Build* builds the PyInstaller sidecar, then `tauri build --bundles deb` on Ubuntu, and uploads the `.deb`. Integration tests are not run in CI (network).

---

## 12. Implementation Phases

**Phase 1 — Backend core + auth**
Structure, config, logging, DB, server (token auth, CORS), AuthService, YouTubeService, auth + search endpoints.
*Verify*: server starts on 127.0.0.1; search works unauthenticated; browser-cookie import signs in; liked songs load.

**Phase 2 — DASH streaming core**
`dash.py` parser, manifest fetch, segment table, DownloadManager, atomic verified downloads, LRU cache + reconciliation, Range-capable audio endpoint, buffer-ahead, epoch seek.
*Verify*: with one pinned song — first audio < 300 ms; `curl -r 0-1023` returns 206 with correct bytes; seek works; second launch serves from cache instantly.

**Phase 3 — Tauri shell + player**
sidecar spawn + token, ApiClient, PlayerBar + SegmentBar, Search/Library/Auth pages, queue state.
*Verify*: play/pause/seek/next from the UI; segment bar updates; auth flow works from the UI.

**Phase 4 — Polish**
Logs page, MSE upgrade (optional, §8.4), error surfacing (expired session, unplayable song), settings persistence.

**Phase 5 — Packaging + tests**
PyInstaller sidecar, `tauri build`, full test suite green, README.

**Status**: Phases 1–5 are implemented. The full suite is green, and the PyInstaller sidecar and `tauri build` work (the latter since Revision 8). The DASH path (Phase 2's core), the G1 latency target and packaged-sidecar runtime are not met yet; the [improvement plan](improvement-plan/README.md) (refactoring phases 0–6) tracks the remaining work, and Phase 0 is done.

---

## Appendix — Glossary (delta from v1)

| Term | Definition |
|---|---|
| **Segment** | A unit of cached audio taken from YouTube's DASH manifest (init segment + media segments). Replaces v1's "chunk". |
| **Init segment** | The small header segment (ftyp/moov or EBML/Tracks). Required for decoding; concatenated with media segments it forms a valid playable file. |
| **Segment table** | Per-song, exact mapping of segment index → byte range + duration, parsed from the MPD. |
| **Epoch** | Per-song monotonic counter bumped on seek; invalidates in-flight downloads from before the seek. |
| **SAPISIDHASH** | `SHA1(ts + " " + __Secure-3PAPISID + " " + origin)` — YouTube Music's cookie-derived auth header. |
| **itag 140 / 251** | YouTube format codes: AAC 128 kbps MP4 / Opus ~160 kbps WebM. v2 defaults to 140. |