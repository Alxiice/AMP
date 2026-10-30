# AMP v2

YouTube Music streaming desktop app with DASH-segment caching. Tauri shell + React frontend + FastAPI backend sidecar.

> **Personal prototype. Not for distribution.** Cookie-based YouTube extraction is against YouTube's ToS; accepted risk for this project.

## Features

- **Works out of the box** — no sign-in required. Search, browse, and play YouTube Music immediately
- **DASH-segment streaming**: Audio is cached as individual segments from YouTube's own DASH manifest, enabling instant seeks and persistent cache
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
│  BackendSidecar (spawn + health)   │                     │
└────────────────────────────┬───────┴─────────────────────┘
                             │ HTTP, 127.0.0.1:8000 (open by default)
┌────────────────────────────▼─────────────────────────────┐
│  FastAPI Backend (Python, sidecar process)               │
│  AuthRoutes · Endpoints · Logs/Health                    │
│  Services: AuthService · YouTubeService · StreamingService│
│    ├── SegmentFetcher (yt-dlp → manifest URL)            │
│    ├── ManifestParser (MPD → segment table)              │
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

The app uses this virtualenv automatically — the Tauri frontend spawns `venv/Scripts/python.exe` (Windows) or `venv/bin/python` (Unix).

### Backend

```bash
# Run without a token (open mode — search and streaming work immediately)
python -m backend.main --debug

# Or with a token (all requests require Authorization: Bearer <token>)
python -m backend.main --token my-secret-token --debug
```

### Authentication (optional)

The app works without any sign-in. To access your liked songs and playlists:

1. Open the **Auth** page in the app
2. Either import cookies from your browser or paste a Cookie header from music.youtube.com
3. Your session is saved to `.amp/cache/ytm_session.json` (0600 permissions)

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
| `PORT` | `8000` | Bind port |
| `AUTH_TOKEN` | _(none)_ | Optional Bearer token (CLI `--token`). If set, all requests require it |
| `CACHE_MAX_SIZE_MB` | `500` | LRU eviction threshold |
| `SEGMENT_BUFFER_AHEAD_SEC` | `30` | Pre-fetch window |
| `STREAM_FORMAT` | `140` | itag (140=AAC/MP4, 251=Opus/WebM) |
| `DOWNLOAD_WORKERS` | `4` | Download thread pool size |
| `MAX_RETRIES` | `3` | Retry attempts per segment |

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
| POST | `/api/stream/{id}/play` | Start playback + buffer |
| POST | `/api/stream/pause` | Pause |
| POST | `/api/stream/resume` | Resume |
| POST | `/api/stream/stop` | Stop |
| POST | `/api/stream/position?position_ms=` | Update playhead |
| POST | `/api/stream/seek?position_ms=` | Seek + re-buffer |
| GET | `/api/stream/playback-state` | Current playback state |
| GET | `/api/stream/logs` | Streaming log lines |
| GET | `/api/auth/status?verify=` | Auth status |
| POST | `/api/auth/cookies` | Set cookies |
| POST | `/api/auth/import-browser?browser=` | Import from browser |
| POST | `/api/auth/logout` | Logout |

## Testing

```bash
# Unit tests (no network)
pytest -m "not integration"

# Integration tests (network + cookies, ~2 min)
pytest -m integration
```

Pinned songs: `dQw4w9WgXcQ` (Rick Astley), `LTDxBgP0lqA` (The Weeknd).

## Project Structure

```
amp/
├── backend/
│   ├── main.py              # Entry point
│   ├── config.py            # pydantic-settings
│   ├── api/
│   │   ├── server.py        # FastAPI app, auth middleware, CORS
│   │   ├── endpoints.py     # Library + streaming + logs routes
│   │   └── auth_routes.py   # Auth endpoints
│   ├── services/
│   │   ├── auth.py          # AuthService, CredentialStore, SAPISIDHASH
│   │   ├── youtube.py       # YouTubeService (ytmusicapi)
│   │   └── streaming.py     # StreamingService, DownloadManager, cache
│   ├── database/
│   │   ├── models.py        # SQLAlchemy models
│   │   └── session.py       # Engine (WAL), session factory
│   ├── utils/
│   │   ├── logger.py        # File + ring buffer logging
│   │   └── dash.py          # MPD parser (pure functions)
│   └── tests/               # Unit + integration tests
├── frontend/
│   ├── src/
│   │   ├── api.ts           # Typed fetch wrapper
│   │   ├── sidecar.ts       # Backend process management
│   │   ├── state.ts         # Queue + playback state
│   │   ├── components/      # PlayerBar, SegmentBar, SongList
│   │   └── pages/           # Search, Library, Playlists, Auth, Logs
│   ├── index.html           # CSP meta
│   └── src-tauri/           # Tauri v2 config
├── .amp/                    # Runtime: cache/, logs/ (gitignored)
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Security

- Binds to `127.0.0.1` only — never exposed to LAN
- Host header validation always enforced (DNS-rebinding guard)
- Bearer token optional — set `AUTH_TOKEN` / `--token` to require it on every request
- Explicit CORS origins (never `*` with credentials)
- CSP in the webview
- YouTube credentials stored with `0600` permissions
- yt-dlp cookie temp files are `0600` and deleted in `finally`

## License

Personal prototype. Not for distribution.
