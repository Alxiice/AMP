# AMP v2

YouTube Music streaming desktop app with DASH-segment caching. Tauri shell + React frontend + FastAPI backend sidecar.

> **Personal prototype. Not for distribution.** Cookie-based YouTube extraction is against YouTube's ToS; accepted risk for this project.

## Features

- **Works out of the box** — no sign-in required. Search, browse, and play YouTube Music immediately
- **DASH-segment streaming**: Audio is cached as individual segments read from the stream's own fMP4 index (`sidx`), enabling exact seeks and a persistent cache
- **< 300ms time to first audio**: Init segment + first media segment are queued at CRITICAL priority
- **Real HTTP Range support**: The local audio endpoint implements Range correctly — the browser's `<audio>` element seeks via Range requests
- **Persistent segment cache**: Segments survive restarts; LRU eviction at 500 MB
- **Buffer-ahead**: Pre-fetches 30 seconds ahead of the playhead with 4 download workers
- **Epoch-based seek cancellation**: Stale in-flight downloads are discarded on seek
- **Optional auth**: Cookie-based sign-in (SAPISIDHASH) unlocks liked songs and user playlists — search and streaming work without it

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Tauri App (React + TypeScript + Vite)                   │
│  PlayerBar · Search · Library · Playlists · Auth · Logs  │
│  HTMLAudioElement ←── HTTP Range ──┐                     │
│  ApiClient (fetch, optional token) │                     │
│  sidecar.ts (backend_info, health) │                     │
│  Rust backend.rs: spawn, free port, stop on exit         │
└────────────────────────────┬───────┴─────────────────────┘
                             │ HTTP, 127.0.0.1:<free port> (open by default)
┌────────────────────────────▼─────────────────────────────┐
│  FastAPI Backend (Python, sidecar process)               │
│  AuthRoutes · Endpoints · Logs/Health                    │
│  Services: AuthService · YouTubeService · StreamingService│
│    ├── StreamExtractor (yt-dlp → stream URL)             │
│    ├── Index parser (fMP4 sidx → segment table)          │
│    ├── DownloadManager (4 workers, priority queue)       │
│    └── PlaybackSession (in-memory, epoch-based)          │
└────────────────────────────┬─────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────┐
│  SQLite (userdb.sqlite) + filesystem cache               │
│  .amp/cache/segments/{song_id}/init.bin, 0000.bin, ...   │
└──────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+ (required by yt-dlp for JS challenges)
- Rust toolchain (for Tauri dev)

### Virtualenv

Create a Python virtualenv and install dependencies:
```bash
cd amp/
python -m venv venv
# Windows:
. venv\Scripts\activate
# Unix:
source venv/bin/activate
pip install -r requirements.lock
```

`requirements.lock` pins exact versions (a known-good set that passes the test
suite). `requirements.txt` holds the looser ranges it was generated from.

**Upgrading yt-dlp.** yt-dlp is the one dependency that must track YouTube
changes, so it is not capped. To upgrade it:
```bash
pip install -U "yt-dlp[default]"
python -m pytest backend/tests/test_integration_download.py -m integration -v -s
```
If the integration download test passes, regenerate the lock file with
`pip freeze > requirements.lock`. The `[default]` extra installs `yt-dlp-ejs`,
the JS challenge solver; with Node.js on `PATH` the backend logs both as found at startup.

The desktop app's dev build uses this virtualenv automatically: Rust (`src-tauri/src/backend.rs`)
spawns `venv/Scripts/python.exe` (Windows) or `venv/bin/python` (Unix). Set `AMP_PYTHON` to use
another interpreter.

## Running the app

**The Tauri app is the normal entry point.** It starts its own backend and stops it when it exits:

- Port: a free port picked at launch (set `AMP_PORT` to fix it, e.g. `AMP_PORT=8000` for
  bookmarked `/docs` URLs). The frontend asks Rust for it (`backend_info`); the CSP allows any
  `127.0.0.1` port.
- Data: the per-user app data dir — `%APPDATA%\com.amp.v2\` (Windows),
  `~/Library/Application Support/com.amp.v2/` (macOS), `~/.local/share/com.amp.v2/` (Linux):
  `cache/` (segments, `ytm_session.json`), `logs/` (`app.log`, `streaming.log`, rotated at 5 MB × 3),
  `userdb.sqlite`, `backend.pid`. Sign-ins from `amp/.amp/` are **not** copied: sign in again
  (the dev backend logs a hint when it sees one).
- Lifetime: the backend runs with `--parent-watch` and exits when the app's stdin pipe closes,
  so it also goes away when the app is killed. Closing the window asks it to exit, then kills
  its process tree after 2 s.
- One instance: launching the app again focuses the running window (two backends must not
  share one segment cache).
- Backend output: the **Logs** page, "Backend stdout" tab.

`app.py` (tkinter) is a **debugging tool**: it runs a backend on `:8000` (or `AMP_PORT`) with
the checkout's `amp/.amp/` + `amp/userdb.sqlite`, the Vite web app, an API tester and a chunk
viewer. Its Force Kill uses `amp/.amp/backend.pid` first, then port scanning.

### Packaging

```bash
cd amp/
python scripts/build_sidecar.py --smoke   # PyInstaller → frontend/src-tauri/binaries/amp-backend-<triple>[.exe]
cd frontend && npx tauri build            # installers in src-tauri/target/release/bundle/{msi,nsis}/
```

`build_sidecar.py` runs PyInstaller on `amp-backend.spec`, names the binary after `rustc -vV`'s
host triple (what `externalBin` expects) and, with `--smoke`, starts it on a free port, checks
`/api/health` + a search and that it exits on stdin EOF. Tauri needs that file even for
`tauri dev` (the dev build itself runs the venv). **Rebuild the sidecar after every yt-dlp
upgrade.** Node.js is not bundled: it must be on `PATH` (`/api/health` reports it, and playback
fails with "Node.js not found" otherwise).

### Backend

```bash
# Run without a token (open mode — search and streaming work immediately)
python -m backend.main --debug

# Or with a token (all requests require Authorization: Bearer <token>)
python -m backend.main --token my-secret-token --debug

# As the desktop app runs it: free port, its own data dir, exit when stdin closes
python -m backend.main --port 0 --data-dir /tmp/amp-data --parent-watch
```

Without `--data-dir`, data stays in `amp/.amp/` and `amp/userdb.sqlite` (the sidecar binary
defaults to the app data dir instead). The backend writes `<data dir>/backend.pid`
(`{"pid", "port", "started_at"}`) and warns at startup if the backend recorded there is still alive.

### Authentication (optional)

The app works without any sign-in. To access your liked songs and playlists:

1. Open the **Auth** page (or click the session badge in the sidebar)
2. Click **Sign in with YouTube** and sign in in the window that opens (desktop app only)
3. Fallbacks under **Advanced**: paste a Cookie header copied from DevTools, or import from Firefox (close Firefox first; Chrome/Edge cookies can't be decrypted on Windows)
4. Only youtube.com cookies are saved, to `<data dir>/cache/ytm_session.json` (0600 permissions). Older files that held a whole browser jar are trimmed on startup; sign in again if the Auth page asks you to

### Frontend (dev)

```bash
cd amp/frontend/
npm install
npm run dev
```

### Tauri (desktop app)

```bash
cd amp/frontend/
npm run tauri dev
```

## Configuration

All settings via environment variables or `.env`:

| Setting | Default | Description |
|---|---|---|
| `HOST` | `127.0.0.1` | Bind host (never `0.0.0.0`) |
| `PORT` | `8000` | Bind port (CLI `--port`; `0` = any free port). The desktop app picks one |
| `AMP_PORT` | _(none)_ | Desktop app and `app.py`: use this port instead of a free one / 8000 |
| `AMP_PYTHON` | `amp/venv/...` | Desktop app (dev build): Python used to run the backend |
| `AUTH_TOKEN` | _(none)_ | Optional Bearer token (CLI `--token`). If set, all requests require it |
| `CACHE_MAX_SIZE_MB` | `500` | LRU eviction threshold |
| `SEGMENT_BUFFER_AHEAD_SEC` | `30` | Pre-fetch window |
| `STREAM_FORMAT` | `140` | itag (140=AAC/MP4, 251=Opus/WebM) |
| `YTDLP_PLAYER_CLIENTS` | `["visionos","default"]` | yt-dlp player clients tried in order (JSON in env); `default` = yt-dlp's choice |
| `DOWNLOAD_WORKERS` | `4` | Download thread pool size |
| `MAX_RETRIES` | `3` | Retry attempts per segment |
| `SEGMENT_SYNC_TIMEOUT_S` | `15` | How long `/audio` waits for a segment before failing |

## API

By default, the API is **open** — no authentication required. If `AUTH_TOKEN` is set, all endpoints under `/api` require `Authorization: Bearer <token>` except `GET /` and `GET /api/health`.

User-specific endpoints (`/api/user/likes`, `/api/user/playlists`) require YouTube cookie auth regardless of token — they return 401 when signed out.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | Health check (no auth) |
| GET | `/api/search?q=&type=&limit=` | Search YouTube Music |
| GET | `/api/song/{id}` | Song metadata |
| GET | `/api/user/likes` | Liked songs (auth) |
| GET | `/api/user/playlists` | User playlists (auth) |
| GET | `/api/stream/info/{id}` | Segment table summary |
| GET | `/api/stream/{id}/audio` | Audio stream (full Range support) |
| GET | `/api/stream/{id}/chunks` | Segment status list |
| POST | `/api/stream/{id}/play` | Resolve the stream, start playback + buffer (returns duration, segment count, `cached_ahead`) |
| POST | `/api/stream/buffer/{id}?mode=current\|prefetch` | Force buffer-ahead, or warm up the next song (LOW priority) |
| POST | `/api/stream/pause` | Pause |
| POST | `/api/stream/resume` | Resume |
| POST | `/api/stream/stop` | Stop |
| POST | `/api/stream/position?position_ms=` | Update playhead |
| POST | `/api/stream/seek?position_ms=` | Seek + re-buffer |
| GET | `/api/stream/playback-state` | Current playback state |
| GET | `/api/stream/logs` | Streaming log lines |
| GET | `/api/auth/status?verify=` | Auth status |
| POST | `/api/auth/tauri-cookies` | Cookies from the sign-in webview |
| POST | `/api/auth/cookies` | Set cookies from a pasted Cookie header |
| POST | `/api/auth/import-browser?browser=firefox` | Import from Firefox (only browser accepted) |
| POST | `/api/auth/logout` | Logout |

## Testing

```bash
# Unit tests (no network)
pytest -m "not integration"

# Integration tests (network + cookies, ~2 min)
pytest -m integration

# Frontend unit tests (pure player helpers, vitest)
cd frontend && npm test
```

Pinned songs: `dQw4w9WgXcQ` (Rick Astley), `LTDxBgP0lqA` (The Weeknd).

## Project Structure

```
amp/
├── backend/
│   ├── main.py              # Entry point (--port, --data-dir, --parent-watch)
│   ├── lifecycle.py         # Socket bind, backend.pid, parent watch
│   ├── config.py            # pydantic-settings, data dir
│   ├── api/
│   │   ├── server.py        # FastAPI app, auth middleware, CORS
│   │   ├── errors.py        # {detail: {code, message}} error model
│   │   ├── endpoints.py     # Library + streaming + logs routes
│   │   └── auth_routes.py   # Auth endpoints
│   ├── services/
│   │   ├── auth.py          # AuthService, CredentialStore, SAPISIDHASH
│   │   ├── youtube.py       # YouTubeService (ytmusicapi)
│   │   ├── extractor.py     # StreamExtractor (single-flight yt-dlp)
│   │   └── streaming/       # facade, registry, downloader, cache, serving, playback
│   ├── database/
│   │   ├── models.py        # SQLAlchemy models
│   │   └── session.py       # Engine (WAL), session factory
│   ├── utils/
│   │   ├── logger.py        # File + ring buffer logging
│   │   ├── mp4.py           # fMP4 sidx parser (pure functions)
│   │   └── layout.py        # Segment table types + byte-range math
│   └── tests/               # Unit + integration tests
├── frontend/
│   ├── src/
│   │   ├── api.ts           # Typed fetch wrapper
│   │   ├── sidecar.ts       # Backend client: backend_info, health poll, log events
│   │   ├── state.ts         # Queue + playback state
│   │   ├── components/      # PlayerBar, SongList
│   │   ├── player/          # error text, queue persistence, prefetch (vitest: npm test)
│   │   └── pages/           # Search, Library, Playlists, Auth, Logs
│   ├── index.html           # CSP meta
│   └── src-tauri/           # Tauri v2: backend.rs (spawns/stops the backend), youtube_login.rs
├── scripts/build_sidecar.py # PyInstaller sidecar → src-tauri/binaries/ (+ --smoke)
├── app.py                   # Debug launcher (tkinter)
├── amp-backend.spec         # PyInstaller spec
├── .amp/                    # Runtime for manual/app.py runs: cache/, logs/ (gitignored)
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Security

- Binds to `127.0.0.1` only — never exposed to LAN
- Host header validation always enforced (DNS-rebinding guard), IPv6 loopback `[::1]` included
- Cross-site requests refused in every mode: POST/PUT/DELETE with a foreign `Origin`, and cross-site GETs on `/api/auth/*` (403 `forbidden_origin`)
- Bearer token optional — set `AUTH_TOKEN` / `--token` to require it on every request
- Explicit CORS origins (never `*` with credentials)
- CSP in the webview; the webview has no `shell:*` permission (the backend is spawned from Rust)
- YouTube credentials stored with `0600` permissions
- yt-dlp cookie temp files are `0600` and deleted in `finally`

## License

Personal prototype. Not for distribution.
