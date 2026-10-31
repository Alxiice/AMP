# AMP v2 — Design Document (Tauri web frontend, DASH-segment streaming)

> **Purpose**: Authoritative spec for AMP v2. An agent reading only this document should be able to build the project. Where v1 was exploratory, this version is prescriptive: decisions are made, alternatives are named only where they remain open.

> **Status (2026-10-31)**: Phases 1–5 below are implemented, and so are refactoring phases 0–6 (AGENTS.md Revisions 7–14; the plan files were removed in Revision 15 and remain in git history). Progress: [AGENTS.md](AGENTS.md). Readable usage guide and code reference: [docs/](docs/index.md) (MkDocs).

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
│  sidecar.ts (backend_info, health) │                     │
│  Rust backend.rs: spawn, free port, stop on exit         │
└────────────────────────────┬───────┴─────────────────────┘
                             │ HTTP, 127.0.0.1:<free port>, Bearer token (optional)
┌────────────────────────────▼─────────────────────────────┐
│  FastAPI Backend (Python, sidecar process)               │
│  ┌────────────┐ ┌──────────────┐ ┌────────────────────┐  │
│  │ AuthRoutes │ │  Endpoints   │ │  Logs / Health     │  │
│  └────────────┘ └──────────────┘ └────────────────────┘  │
│  Services (thread-safe singletons)                       │
│  ├── AuthService      → cookies, SAPISIDHASH, ytmusicapi │
│  ├── YouTubeService   → search, metadata, likes         │
│  └── StreamingService → segments, cache, playback       │
│      ├── StreamExtractor (yt-dlp → stream URL)          │
│      ├── Index parser (fMP4 sidx → segment table)       │
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

**Data flow (play)**: UI `play(song_id)` → `POST /api/stream/{id}/play` **resolves the stream** (blocks for the extraction on first play) and queues init + segment 0 as CRITICAL → UI sets `audio.src = /api/stream/{id}/audio` unless a newer song was chosen meanwhile → endpoint serves init+segments from cache, downloading missing ones synchronously → browser plays, issues its own Range requests as it buffers → DownloadManager pre-fetches ahead of the playhead.

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
├── mkdocs.yml, docs/           # documentation site (usage + code)
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
│   │   └── auth_routes.py      # auth endpoints (status, cookies, tauri-cookies, Firefox import, logout)
│   ├── services/
│   │   ├── auth.py             # AuthService, CredentialStore, SAPISIDHASH
│   │   ├── youtube.py          # YouTubeService (ytmusicapi wrapper)
│   │   ├── extractor.py        # StreamExtractor: single-flight yt-dlp extraction
│   │   └── streaming/          # service.py (facade), registry.py, downloader.py,
│   │                           # cache.py, serving.py, playback.py
│   ├── database/
│   │   ├── models.py           # Song, Playlist, PlaylistSong, LikedSong, Segment
│   │   └── session.py          # engine (WAL), session factory, init
│   ├── utils/
│   │   ├── logger.py           # app.log + streaming.log (rotated 5 MB × 3) + in-memory ring
│   │   ├── mp4.py              # fMP4 box + sidx parsing (pure functions, unit-testable)
│   │   └── layout.py           # SegmentInfo/StreamInfo + byte-range math (was dash.py)
│   └── tests/                  # unit tests (mocked) + integration tests
├── frontend/
│   ├── src/
│   │   ├── api.ts              # typed fetch wrapper, token header
│   │   ├── sidecar.ts          # backend client: backend_info → port, health poll, log events
│   │   ├── components/         # PlayerBar (incl. segment bar), SongList, ...
│   │   ├── player/             # errors, queue persistence, prefetch threshold (pure, vitest)
│   │   ├── pages/              # Search, Library, Playlists, Auth, Logs
│   │   └── state.ts            # queue + playback state (frontend-owned)
│   ├── public/                 # favicons + site.webmanifest (AMP logo)
│   ├── index.html              # CSP meta, favicon links
│   ├── vite.config.ts
│   ├── src-tauri/              # tauri.conf.json (sidecar, capabilities), icons/, Cargo.lock
│   │   ├── src/backend.rs      # spawns/owns/stops the backend (§8.1)
│   │   └── binaries/           # amp-backend-<target-triple> (PyInstaller output, gitignored)
│   └── package.json
├── .amp/                       # runtime for manual / app.py runs: cache/, logs/ (gitignored)
├── amp-backend.spec            # PyInstaller spec for the sidecar
├── scripts/build_sidecar.py    # PyInstaller → src-tauri/binaries/amp-backend-<triple> (+ --smoke)
├── app.py                      # debug launcher (tkinter)
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
| `PORT` | `8000` | CLI `--port`; `0` = any free port. The desktop app passes a free one (§8.1) |
| `AUTH_TOKEN` | `None` (CLI arg `--token`) | Optional. When set, every request needs `Authorization: Bearer <token>`; when unset the API is open (Host check still enforced) |
| `DEBUG` | `False` | |
| `CACHE_DIR` / `SEGMENTS_DIR` / `LOGS_DIR` | `<data>/cache`, `<data>/cache/segments`, `<data>/logs` | created on import / `configure_paths`. `<data>` = `--data-dir`, else `amp/.amp` from a checkout, else (PyInstaller binary) the per-user app data dir `…/com.amp.v2` |
| `DB_PATH` | `userdb.sqlite` | single DB (playdb dropped — playback state is in-memory). `<data>/userdb.sqlite` with `--data-dir` |
| `CACHE_MAX_SIZE_MB` | `500` | evict down to 80% when exceeded |
| `SEGMENT_BUFFER_AHEAD_SEC` | `30` | how far ahead to pre-fetch |
| `SEGMENT_BEHIND` | `2` | segments kept behind playhead for seek-back |
| `STREAM_FORMAT` | `140` | itag; 251 allowed |
| `YTDLP_PLAYER_CLIENTS` | `["visionos", "default"]` | yt-dlp player clients tried in order; `default` = yt-dlp's choice (§6.2) |
| `DOWNLOAD_WORKERS` | `4` | |
| `HTTP_TIMEOUT_CONNECT_S` / `HTTP_TIMEOUT_READ_S` | `5` / `30` | |
| `MAX_RETRIES` | `3` | backoff 0.5 / 1 / 2 s + jitter |
| `SEGMENT_SYNC_TIMEOUT_S` | `15` | `ensure_segment` wait for a segment owned by another thread (§6.5) |

Computed paths (cache, segments, logs, DB file) are private attributes set by `Settings.configure_paths(data_dir=None, db_file=None)`, which `model_post_init` calls with the defaults above. Tests and `--data-dir` (§8.1) call it to redirect storage; `snapshot_paths()` / `restore_paths()` undo the change. Never monkeypatch the private attributes (§10 P27).

### 5.2 Server (`api/server.py`)

1. Create FastAPI app.
2. **Auth middleware**: every request except `GET /` and `GET /api/health` must carry a `Host` of `127.0.0.1`/`localhost` (DNS-rebinding guard), and — when `AUTH_TOKEN` is configured — `Authorization: Bearer <token>`. Reject otherwise (401/403). Open mode (no token) is the default. The Host is parsed without its port (`[::1]:8000` → `[::1]`). **Cross-site requests** are refused in every mode (403 `{"detail": {"code": "forbidden_origin"}}`): a method other than GET/HEAD/OPTIONS with an `Origin` not in `ALLOWED_ORIGINS` (browsers always send `Origin` on cross-origin POST/PUT/DELETE; requests without `Origin` — curl, the control panel — are allowed), and a GET on `/api/auth/*` with `Sec-Fetch-Site: cross-site` and no allowed `Origin`. `/stream/*/audio` stays open for `<audio>`.
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
- **Only youtube.com cookies are stored, with their domain.** `filter_youtube_cookies(jar)` keeps a cookie only if its domain (leading dot stripped) is `youtube.com` or ends with `.youtube.com`, one per (name, domain). Every entry point goes through `AuthService.set_cookies`, which filters; a pasted `Cookie:` header has no domains and gets `.youtube.com`. For the `Cookie` header (`cookies_by_name`), `.youtube.com` wins over subdomains; the Netscape file for yt-dlp writes each cookie once on its own domain.
- **Sign-in paths**: (1) the Tauri webview (`youtube_login.rs`: incognito window, 10 min timeout, reads cookies of `music.youtube.com` and `www.youtube.com` merged by (name, domain)) → `POST /api/auth/tauri-cookies`; (2) under "Advanced": a pasted Cookie header, and Firefox import via `yt_dlp.cookies.extract_cookies_from_browser()` (no network; Firefox must be closed). Other browsers are refused (400): Chrome/Edge cookies can't be decrypted on Windows (app-bound encryption).
- **Session expiry** is decided only by ytmusicapi 401/403 (`youtube.py`) and `status(verify=True)`. A googlevideo CDN 403 means the signed stream URL expired, not the session (§6.5).
- `SAPISIDHASH = SHA1(ts + " " + __Secure-3PAPISID + " " + "https://music.youtube.com")`.
- `CredentialStore`: `.amp/cache/ytm_session.json`, atomic write (tmp + `os.replace`), `0600`. Format v2: `{"version": 2, "cookies": [{"name", "value", "domain"}]}`. A v1 file (flat `{name: value}`, possibly a whole browser jar) is migrated when loaded (at startup): only an allowlist of YouTube/Google session cookie names is kept (domain `.youtube.com`), the file is rewritten, counts are logged; if it held more than 3× the kept count, a WARNING is logged and `/api/auth/status` reports `migrated_from_full_jar: true` until the next sign-in.
- Lazy `YTMusic` client construction (offline launch must not look like a failed login).
- `get_cookie_header()` feeds both ytmusicapi headers and CDN requests.
- States: `signed_out → signed_in → expired`.

### 5.5 YouTubeService (`services/youtube.py`) — unchanged from v1

Wraps `ytmusicapi`: search, song/artist/album/playlist metadata, liked songs, user playlists. Dataclasses + `to_dict()`. Authenticated calls go through `AuthService.client` (falls back to anonymous for search/metadata).

---

## 6. Streaming Core (segments)

This section replaces v1 §9. The unit of caching is the **segment**, taken from the stream's own index (the fMP4 `sidx`), not a proportionally-computed byte range.

### 6.1 Concepts

A YouTube audio stream URL (from yt-dlp) is a direct googlevideo URL for one file:

- **itag 140 (AAC)** is a **fragmented MP4**: `[ftyp][moov][sidx][moof][mdat][moof][mdat]…`. The `sidx` (Segment Index) lists every fragment's byte size and duration: an exact segment table. The **init segment** is everything before the first fragment (`ftyp + moov + sidx`); `init + segments` concatenated is byte-for-byte the CDN file.
- **itag 251 (WebM/Opus)** keeps its index in `Cues`, which is not parsed: it falls back to proportional chunking with the extracted size and duration (§6.4).

> **History**: v2 originally expected yt-dlp to return a DASH **MPD** manifest and parsed it in `utils/dash.py`. yt-dlp never did, so that path never ran and was removed in refactoring Phase 2 (AGENTS.md Revision 10).

### 6.2 Getting the stream URL + index

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

Then fetch `Range: bytes=0-65535` of the URL with CDN headers (cookie when signed in, §10 P1). For m4a/mp4, parse the index from those bytes (§6.3); if the moov is larger, the parser says how many bytes it needs and the head is re-fetched (at most twice). If there is no usable `sidx`, or its sizes don't add up to the extracted file size, or the stream is WebM → proportional fallback (§6.4). The head bytes already cover the init segment, so they are stored as `init.bin` (saves a request on first play). The extracted stream is cached until its URL expires; refresh on 403 (§6.5).

### 6.3 Index parsing (`utils/mp4.py`)

Pure functions, unit-tested with synthetic boxes and one real header (`tests/fixtures/itag140_head.bin`).

- **Boxes**: 32-bit size + 4-char type; `size == 1` → 64-bit largesize follows; `size == 0` → box runs to end of file. Only boxes in front of the first `moof` are read; `moof`/`mdat` are never parsed.
- **`sidx`** (ISO/IEC 14496-12 §8.16.3): full box, `reference_ID`, `timescale`, `earliest_presentation_time` + `first_offset` (32-bit in v0, 64-bit in v1), `reference_count`, then per reference: 1-bit `reference_type` + 31-bit `referenced_size`, 32-bit `subsegment_duration`, SAP fields. Hierarchical indexes (`reference_type == 1`) are rejected.
- The first fragment starts at `sidx_offset + sidx_size + first_offset`; each following one right after the previous. `init_end = first_fragment_offset − 1`, so `total_bytes == filesize`.
- Durations are rounded cumulatively (`elapsed·1000 // timescale` at each boundary) so they sum exactly to the index's total.
- If the buffer ends early, `NeedMoreData(required_len)` tells the caller how much to re-fetch.

YouTube itag 140 fragments are ~10 s (26 for a 258 s song).

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
    is_dash: bool         # name kept for the API: True = exact table (sidx), False = proportional
    base_url: str
    itag: str
    layout_id: str        # sha256(itag | total_bytes | n_segments | method)[:16], §6.6
```

### 6.4 Proportional fallback (WebM, or no sidx)

Used for WebM (itag 251) and for MP4 streams without a usable `sidx`. Size from extraction (`filesize` or the URL's `clen=`), else HEAD → `Range: bytes=0-0`; duration from extraction (no default — unknown duration = unplayable). Segments = proportional byte ranges of `SEGMENT_TARGET_SEC` (default 5 s), no init segment. Marked `is_dash=False`; everything downstream is identical, but time→segment mapping is approximate.

### 6.5 Segment download pipeline

All per-segment state lives in one place, the **`SegmentRegistry`** (`services/streaming/registry.py`, one lock): `MISSING → QUEUED → IN_FLIGHT → DONE | ERROR`, with the best requested priority and epoch while queued and a `threading.Event` set on completion.

- `request(key, priority, epoch)`: no-op if DONE or IN_FLIGHT; re-ranks a QUEUED entry (new heap item) if the request has a newer epoch or a better priority; queues MISSING / ERROR.
- Workers pop heap items and `claim(key, priority, epoch)`: it only succeeds if that exact item is still current, so superseded duplicates are skipped. The heap is ordered by (priority, newer epoch first, request order).
- Request handlers call **`ensure_segment(song_id, index)`**: DONE → path; IN_FLIGHT → wait on the event (`SEGMENT_SYNC_TIMEOUT_S`, 15 s); otherwise claim it and fetch in the handler's thread (jumping the queue; the queued item is then skipped). Failure or timeout raises `SegmentUnavailable`. No polling.

`fetch_segment()` (`downloader.py`) — the robustness-critical path:

1. **Single owner**: only the caller holding the registry claim downloads a segment, so a worker and a request handler can never fetch the same one at once.
2. **HTTP GET** with `Range: bytes=start-end` and CDN headers (`Cookie` from AuthService — without it, 403, §10 P1). Timeouts from config.
3. **Verify the response**: status must be **206**, `Content-Range` must match the requested range, and received byte count must equal `byte_end - byte_start + 1`. A 200 (range ignored) or short read = failure; never write the file.
4. **Atomic write**: stream into a uniquely named `tempfile.mkstemp(dir=song_dir, prefix="NNNN.", suffix=".tmp")`, fsync, `os.replace()` to the final name (retrying briefly on Windows `PermissionError`). A crash mid-download can never leave a corrupt segment that looks complete, and two writers never share a tmp path.
5. **Record**: insert/update the `segments` DB row and the cache's size map; complete the registry key (wakes waiters).
6. **Retry**: up to `MAX_RETRIES` attempts in the owning thread, backoff 0.5/1/2 s + jitter. Distinguish:
   - **403** → refresh stream URL once (clear song caches, re-extract, rebuild segment table — byte layout may change), then retry. Other 4xx → ERROR, no retry. A CDN 403 **does not touch auth state**: the refresh still extracts with the user's cookies (§5.4).
   - **429 / 5xx / timeout** → backoff and re-queue (transient).
7. After every successful download, `CacheStore.maybe_evict()` — O(1) while under the limit. If the song's layout changed while the bytes were in flight, they are deleted and the key is marked ERROR.

Files: `.amp/cache/segments/{song_id}/init.bin`, `{index:04d}.bin` and `layout.json` (§6.6).

### 6.6 Cache & LRU

- Metadata in `segments` table: `song_id, index, byte_start, byte_end, size_bytes, duration_ms, status, file_path, layout_id, last_accessed` (PK: `song_id, index`). `init_db()` recreates the table if it lacks a column (it is only a cache; reconciliation then removes the files).
- **Cache identity**: segment files are only valid for the byte layout they were cut from. Each song directory holds `layout.json` (`layout_id, method, itag, mime_type, total_bytes, duration_ms, init_range, segments: [[start, end, dur], …]`, written atomically). When a newly built table has a different `layout_id` (e.g. a refresh picked itag 251 instead of 140, or the file changed), the song's directory and DB rows are purged before the new manifest is written. `layout.json` is never counted or evicted by the LRU.
- **LRU** (`CacheStore`, `services/streaming/cache.py`): the LRU clock is file **mtime** — set by the download, bumped by `touch()` whenever a segment is served (at most once per 30 s per file). A per-file size map keeps a running total (full scan only at startup or in `cleanup_cache()`). Over `CACHE_MAX_SIZE_MB` → sort by mtime, evict to 80 %, skipping the playing song's `init.bin` and every segment from `current_index − SEGMENT_BEHIND` on, IN_FLIGHT segments and `layout.json`. Eviction deletes the file and DB row and sets the registry key back to MISSING. (`last_accessed` in the DB is no longer written.)
- **Startup reconciliation**: scan `SEGMENTS_DIR`; a song directory without `layout.json` is deleted (this also clears pre-Phase-2 caches); delete orphan files (no DB row), delete rows with missing files, verify file sizes match `size_bytes` and `layout_id` matches the manifest (mismatch → delete both). This heals any crash damage.
- Startup reconciliation also rebuilds the registry (DONE for every file that matches its `layout.json` and DB row), so `/chunks` is served from memory with no filesystem calls.
- In-memory caches (stream info, extracted streams, failures) are **bounded** dicts (256 entries). v1 leaked these.

### 6.7 Local audio endpoint — real Range support

`GET /api/stream/{song_id}/audio` — this is what the browser's `<audio>` element talks to. **It must implement `Range` correctly** (v1 advertised `Accept-Ranges` but ignored the header — with a browser frontend that bug breaks seeking).

Virtual byte layout: `[init][segment 0][segment 1]...[segment N-1]`. All offsets exact from the segment table.

| Request | Behavior |
|---|---|
| No `Range` header | `200`, full stream, `Content-Length: total_bytes`, `Accept-Ranges: bytes` |
| `Range: bytes=a-b` | `206`, `Content-Range: bytes a-b/total`, `Content-Length: b-a+1` |
| `Range: bytes=a-` | `206`, from `a` to end |
| Unsatisfiable | `416` with `Content-Range: bytes */total` |

Serving (`services/streaming/serving.py`): map the requested byte window to segment files (a window can span segments), reading only the needed byte ranges from disk. **The first segment is `ensure_segment`ed before the response headers are returned**: if it can't be delivered the response is JSON (`502 segment_unavailable`, or 404/401/502/503 from the extraction error code) instead of a 206 promising bytes. A later segment that can't be delivered **raises inside the body generator**, so Starlette aborts the connection (a retryable network error for the browser) — the body is never silently shorter than `Content-Length`. A file evicted between `ensure_segment` and `open` is fetched once more. Content-Type from `StreamInfo.mime_type`. `Cache-Control: no-cache`. Handlers are sync and block in Starlette's threadpool (P21).

### 6.8 Buffer-ahead & priorities

On `POST /api/stream/{song_id}/play` (or first audio request):

- Queue **init** and the **segment at the playhead** at CRITICAL.
- Queue next 2 segments HIGH, then NORMAL until `SEGMENT_BUFFER_AHEAD_SEC` (30 s) of audio **ahead of the playhead** is covered. The window is measured from the playhead segment, not from the song start (accumulate `duration_ms` from the start index, O(n)).
- Keep `SEGMENT_BEHIND` (2) segments behind the playhead cached (don't evict).
- Position reports (every 2 s) only re-request when the playhead entered a new segment since the last buffer-ahead.
- Starting another song unqueues (not cancels) the previous songs' queued segments; stop does the same for the current song. In-flight downloads always finish.
- `DownloadManager`: `PriorityQueue` + `ThreadPoolExecutor(4)`, started at app startup, shut down on app shutdown. The heap only holds hints; the registry decides.

### 6.9 Seek — epoch-based priority

`seek(position_ms)`:

1. Bump the song's **epoch** (monotonic counter).
2. Map `position_ms → segment index` via the segment table (exact durations with a sidx table).
3. Request from the new position with buffer-ahead priorities and the new epoch.

The epoch is a **priority**, not a cancellation: the new requests outrank everything queued before the seek (a still-queued segment is re-ranked, not dropped — the pre-Phase-3 bug was that it was silently skipped until the next position report). Downloads already in flight finish, because their bytes are valid. (Before Phase 3, stale workers were meant to "discard" results, but the file was written regardless.)

### 6.10 PlaybackSession (in-memory)

`PlaybackInfo`: `song_id, current_segment_index, position_ms, is_playing, volume, epoch, last_updated`. `position_ms` is reported by the frontend every 2 s (`POST /api/stream/position`) and drives buffer-ahead. Not persisted — playback state is frontend-owned.

---

## 7. API Specification

All under `/api`. When a token is configured, all require it except `GET /` and `GET /api/health` (§5.2). All blocking handlers are plain `def`. Also implemented: `GET /api/stream/cache-info`.

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
| POST | `/api/stream/{id}/play` | resolve stream, start session + buffer → `{song_id, duration_ms, mime_type, segment_count, is_dash, epoch, cached_ahead}` |
| POST | `/api/stream/pause` , `/resume` , `/stop` | `{message}` |
| POST | `/api/stream/position?position_ms=` | update playhead |
| POST | `/api/stream/seek?position_ms=` | seek + re-buffer (§6.9) |
| POST | `/api/stream/buffer/{id}?mode=current\|prefetch` | `current`: force buffer-ahead; `prefetch`: resolve + init and 2 segments at LOW, session untouched |
| GET | `/api/stream/playback-state` | `PlaybackInfo` |
| GET | `/api/stream/logs` | recent streaming log lines |
| GET | `/api/auth/status?verify=` | `{state, is_authenticated, account, migrated_from_full_jar}` |
| POST | `/api/auth/tauri-cookies` | `{cookies: [{name, value, domain}]}` from the sign-in webview; 400 if none is a youtube.com cookie |
| POST | `/api/auth/cookies` , `/cookie-header` | `{cookie_header}` pasted from DevTools (domain `.youtube.com`) |
| POST | `/api/auth/import-browser?browser=firefox` | Firefox only (400 for other browsers, 404 if no YouTube cookies) |
| POST | `/api/auth/logout` | clear the stored session |
| GET/POST/DELETE | `/api/logs` | frontend log relay (last 500) |

**Errors** (streaming routes, `api/errors.py`): `{"detail": {"code", "message"}}` — `invalid_id` 400, `unavailable` / `no_audio` 404, `auth_required` 401, `node_missing` 503, `extract_failed` / `segment_unavailable` 502, `bad_range` 416. Library routes still use string `detail`s. There is no readiness-polling route: `/play` returning means the stream is resolved.

Response shapes are consumed directly by the TypeScript client (`frontend/src/api.ts` defines the types). No v1-style bridge normalization layer — the frontend adapts.

**Dropped from v1**: queue endpoints, `playdb`, legacy `/api/playback/*` (frontend owns the queue), dashboard HTML (logs endpoints suffice; a simple Logs page in the app replaces it).

---

## 8. Frontend (Tauri + React)

### 8.1 Lifecycle

**Rust owns the backend** (`src-tauri/src/backend.rs`); the webview has no `shell:*` permission.

- `setup()`: port = `AMP_PORT` or a free port (bind `127.0.0.1:0`, drop); data dir = `app.path().app_data_dir()` (`%APPDATA%\com.amp.v2` on Windows). Spawn with `--host 127.0.0.1 --port <p> --data-dir <dir> --parent-watch`: in debug builds `<amp>/venv` Python (or `AMP_PYTHON`) `-m backend.main` from `amp/`; in release builds the PyInstaller sidecar `amp-backend` (`tauri.conf.json → bundle.externalBin`, file `src-tauri/binaries/amp-backend-<target-triple>[.exe]`, built by `scripts/build_sidecar.py`). `set_process_group(true)` (a Windows job object): the venv launcher and the PyInstaller bootloader both start a second process. The environment is inherited (Node must stay on `PATH`), plus `PYTHONIOENCODING=utf-8`.
- Output: stdout/stderr lines decoded with `String::from_utf8_lossy` (P7), kept in a 1000-line ring (`backend_logs`) and emitted as `backend-log`; `Terminated` of the current backend → `backend-status {state: "stopped"}`.
- Commands: `backend_info() → {port, token}` (token always `null` until per-launch tokens (AGENTS.md Known Issues) are done), `backend_logs()`, `restart_backend()`.
- Exit (`RunEvent::Exit`): write `exit` to the backend's stdin, wait ≤ 2 s, then kill the process tree.
- **Parent watch** (`--parent-watch`): a daemon thread reads stdin; EOF (the app died, even from the Task Manager) or `exit` → graceful uvicorn shutdown, `os._exit` after 1.5 s at the latest.
- `<data>/backend.pid` = `{pid, port, started_at}`, removed on exit. At startup a WARNING is logged if the recorded backend still answers `/api/health` with that `pid` (`app: "AMP v2"`). `app.py` uses it for Force Kill.
- One instance (`tauri-plugin-single-instance`): a second launch focuses the running window. Two backends must not share one segment cache.
- Frontend (`sidecar.ts`): `initBackend()` runs before the first render and sets `api.ts`'s base URL from `backend_info`; then the health poll (1 s, in-flight guard), the log ring and the events; restart button → `restart_backend` (the port may change). Outside Tauri (Vite in a browser) the base URL stays `http://127.0.0.1:8000` and the backend is started by hand or by `app.py`.
- Node.js is not bundled; `/api/health` reports it (P2).

### 8.2 Pages / components

| Component | Purpose |
|---|---|
| `PlayerBar` (persistent) | play/pause/stop, time, volume, thumbnail/title; segment bar (one cell per segment, colored by status, click-to-seek; `/chunks` polled at 500 ms **with an in-flight guard**, §10 P12). Load sequence: `/play` (abortable) → generation check → `audio.src`; error codes mapped to text (`player/errors.ts`); one reload after a mid-stream network error; TTFA logged to the API relay |
| `Search` | query box, results list, play per result |
| `Library` | liked songs list; "Sign in to see your library" when signed out / on 401 |
| `Playlists` | user playlists as cards (no track view yet); same sign-in prompt |
| `Auth` | three things: status (+ migration warning), "Sign in with YouTube" (Tauri webview), collapsed "Advanced" (paste Cookie header, Firefox import) |
| Sidebar | session badge `Signed in` / `Signed out` / `Session expired — reconnect` → `/auth`; `/api/auth/status` polled every 60 s (in-flight guard) and after any 401 from `/api/user/*` (`authSession.ts`) |
| `Logs` | backend stdout, streaming logs, API log relay |

Queue state (list of songs, current index, next/previous) is **frontend-owned** in `state.ts` — no backend queue API. Songs, current index and volume persist in `localStorage` (`amp.queue.v1`, debounced 500 ms) and are restored paused. When < 20 s remain or past 80 % of the current song, the next song is prefetched once (`/buffer?mode=prefetch`).

### 8.3 Player

```ts
const audio = new Audio(`${baseUrl}/api/stream/${songId}/audio`); // baseUrl from backend_info
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
connect-src 'self' http://127.0.0.1:*;
media-src 'self' http://127.0.0.1:*;
img-src 'self' https://i.ytimg.com https://*.ggpht.com https://lh3.googleusercontent.com data:;
style-src 'self' 'unsafe-inline';
```

The same policy is set in `tauri.conf.json → app.security.csp`. `media-src` is required for `<audio>` to load from the backend; `lh3.googleusercontent.com` serves YouTube Music thumbnails. Favicons and the web manifest are same-origin (`frontend/public/`), covered by `default-src 'self'`.

The port is chosen at launch, hence `127.0.0.1:*`. Tauri v2 capabilities: `core:default` only — no `shell:*` (the backend is spawned from Rust), no fs.

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
- **P7 — Windows encoding.** Decode subprocess output as UTF-8 with replacement: Python side `decode("utf-8", errors="ignore")` (`app.py`); Tauri side `String::from_utf8_lossy` + `PYTHONIOENCODING=utf-8` for the backend (§8.1).
- **P9 — FastAPI route order.** Specific routes before parameterized (`/stream/logs` before `/stream/{song_id}`).
- **P11 — localStorage is origin-scoped.** Cross-port sharing needs the server-side relay (`POST /api/logs` → `GET /api/logs`). (Kept for reference; v2's UI is same-app, but the relay stays.)
- **P12 — Overlapping polls.** Guard every polling timer with an in-flight flag.

New in v2 (from the v1 review):

- **P13 — `song_id` is a path parameter.** Validate against `^[A-Za-z0-9_-]{11}$` before using it in file paths. Path traversal otherwise.
- **P14 — Verify 206 + Content-Range + byte count.** A range-ignoring 200 saved as a segment silently corrupts the cache.
- **P15 — Atomic writes only.** tmp file + `os.replace()`. A crash must never leave a partial segment that looks complete.
- **P16 — Implement Range for real.** The browser's `<audio>` seeks via Range. Advertising `Accept-Ranges` without honoring the header breaks seeking.
- **P17 — Bind `127.0.0.1`, require the token, validate `Host`.** The API reads the user's YouTube session (liked songs) and controls playback. v1's `0.0.0.0` + `CORS *` + no auth let any LAN peer or any open webpage drive it.
- **P18 — Seek needs an epoch.** Bump a per-song epoch on seek; requests with the newer epoch outrank everything queued before it. In-flight downloads finish (their bytes are valid); queued ones are re-ranked, never dropped.
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

New from refactoring Phase 5 (AGENTS.md Revision 13):

- **P29 — Open mode needs an Origin check.** CORS only stops a page from *reading* the response; a cross-site `fetch(..., {method: "POST"})` with no body is sent without a preflight and runs. Refuse non-safe methods whose `Origin` isn't allowed (§5.2).
- **P30 — Keep cookie domains.** Flattening cookies to `{name: value}` loses which site they belong to and lets another site's `SID` overwrite YouTube's. Store `(name, value, domain)` (§5.4).

---

## 11. Testing

- **Unit** (`pytest -m "not integration"`, fully mocked, no network): config, models, `mp4.py` index parser (synthetic boxes, sidx v0/v1, truncation, plus a real itag 140 header fixture), `extractor.py`, layout identity, segment byte-range math, Range-header mapping (§6.7), auth (SAPISIDHASH, CredentialStore), SegmentRegistry state machine, DownloadManager ordering/superseded items, `fetch_segment` verification + unique tmp files, CacheStore LRU/accounting, serving (no short bodies), playback policy, endpoints (TestClient), lifecycle (`--data-dir`, PID file, socket bind, rotating log handlers, and a real `python -m backend.main --parent-watch` process that must exit within 3 s of stdin EOF). Rust: `cargo test` (`free_port_is_bindable`).
- **Integration** (`pytest -m integration`, network, ~2 min, cookies optional): `test_integration.py` pins `dQw4w9WgXcQ` (Rick Astley) and `LTDxBgP0lqA` (The Weeknd — Blinding Lights); `test_integration_download.py` downloads every segment of `BAgTQhR8MLo` (override with `AMP_TEST_SONG_ID`, e.g. `Tmz3mpOq8aE`). Both must handle streams without an init segment (`has_init=False`). If a pinned song breaks (removed/region-blocked), update the ID — accepted per scope. Run after every yt-dlp upgrade.
  - manifest fetch + parse end-to-end
  - init + first 3 segments download, sizes verified
  - full audio endpoint: `Range: bytes=0-1023` returns 206 with correct bytes; seek to 50% serves correct segment
  - cache eviction and startup reconciliation with a temp cache dir
- Singletons reset between tests (`conftest.py` clears `_instance` globals); temp dirs for cache/DB via the `temp_dirs` fixture (`configure_paths` / `restore_paths`, §10 P27); integration tests copy cookies to `ytm_session.json` and clean up.
- **Lint**: `ruff check amp/backend/` with `.ruff.toml` (pyflakes, pycodestyle errors, bugbear, bandit; tests excluded). Inline `noqa` must give a reason.
- **Coverage**: `pytest -m "not integration" --cov=backend` (config in `amp/pyproject.toml`, tests omitted, branch coverage). `fail_under = 60` is a regression floor; raise it as coverage grows.
- **CI** (GitHub Actions, every push and PR): *Python CI* installs `requirements.lock`, runs Ruff, unit tests with coverage, uploads to Codecov. *Tauri Build* builds the PyInstaller sidecar with `scripts/build_sidecar.py --smoke` (health + search + exit on stdin EOF), then `tauri build --bundles deb` on Ubuntu, and uploads the `.deb`. Integration tests are not run in CI (network).

---

## 12. Implementation Phases

**Phase 1 — Backend core + auth**
Structure, config, logging, DB, server (token auth, CORS), AuthService, YouTubeService, auth + search endpoints.
*Verify*: server starts on 127.0.0.1; search works unauthenticated; browser-cookie import signs in; liked songs load.

**Phase 2 — DASH streaming core**
Segment table (originally an MPD parser; now the fMP4 `sidx`, refactoring Phase 2 (AGENTS.md Revision 10)), DownloadManager, atomic verified downloads, LRU cache + reconciliation, Range-capable audio endpoint, buffer-ahead, epoch seek.
*Verify*: with one pinned song — first audio < 300 ms; `curl -r 0-1023` returns 206 with correct bytes; seek works; second launch serves from cache instantly.

**Phase 3 — Tauri shell + player**
sidecar spawn + token, ApiClient, PlayerBar (with segment bar), Search/Library/Auth pages, queue state.
*Verify*: play/pause/seek/next from the UI; segment bar updates; auth flow works from the UI.

**Phase 4 — Polish**
Logs page, MSE upgrade (optional, §8.4), error surfacing (expired session, unplayable song), settings persistence.

**Phase 5 — Packaging + tests**
PyInstaller sidecar, `tauri build`, full test suite green, README.

**Status**: Phases 1–5 are implemented, and refactoring phases 0–6 are done (AGENTS.md Revisions 7–14): exact segment tables from the sidx (Revision 10), G1 met for cached songs (Revision 12), the packaged sidecar starts, plays and stops with the app (Revision 14). Open items are listed under "Known Issues / TODO" in AGENTS.md.

---

## Appendix — Glossary (delta from v1)

| Term | Definition |
|---|---|
| **Segment** | A unit of cached audio: one fMP4 fragment from the `sidx` (or a proportional slice for WebM). Replaces v1's "chunk". |
| **Init segment** | Everything before the first fragment (`ftyp + moov + sidx`). Required for decoding; concatenated with media segments it is byte-for-byte the CDN file. |
| **Segment table** | Per-song mapping of segment index → byte range + duration, parsed from the fMP4 `sidx` (exact) or computed proportionally. |
| **sidx** | ISO BMFF Segment Index box: per-fragment byte size and duration. |
| **layout_id** | Hash of `(itag, total_bytes, segment count, method)`; cached segments under another id are purged. |
| **Epoch** | Per-song monotonic counter bumped on seek; invalidates in-flight downloads from before the seek. |
| **SAPISIDHASH** | `SHA1(ts + " " + __Secure-3PAPISID + " " + origin)` — YouTube Music's cookie-derived auth header. |
| **itag 140 / 251** | YouTube format codes: AAC 128 kbps MP4 / Opus ~160 kbps WebM. v2 defaults to 140. |