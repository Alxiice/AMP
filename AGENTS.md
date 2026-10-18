# AGENTS.md - AMP Project Agent Instructions

> **Purpose**: Instructions for AI agents (or developers) to continue the AMP project across sessions.

---

## How to Use This File

1. **START HERE**: Read this file completely before beginning work.
2. **Understand State**: Check the current implementation status below.
3. **Implement**: Work on the next step in the roadmap.
4. **Update**: After completing work, update this file (mark tasks, update phase, set next steps).
5. **Commit**: Commit changes with the updated AGENTS.md.

---

## Project Overview

**Project**: AMP (Another Music Player)
**Description**: Local music player based on YouTube Music library
**Tech Stack**: FastAPI, React, Tauri, yt-dlp, ytmusicapi, SQLAlchemy, SQLite
**Current Phase**: Phase 3 (Core Playback System) — ✅ COMPLETE
**Next Phase**: Phase 4 (Frontend Buffering) — ⏳ READY TO START
**Tests**: 116/116 passing

---

## Essential Reading

1. **This file** (`AGENTS.md`)
2. **[ROADMAP.md](ROADMAP.md)** — Full roadmap (10 phases)
3. **[README.md](README.md)** — Project overview
4. **[IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md)** — Phase 1 & 2 details
5. **[amp/backend/README.md](amp/backend/README.md)** — Backend guide
6. **[CONTRIBUTING.md](CONTRIBUTING.md)** — Dev setup, WSL2 cross-compilation — Backend guide

Optional:
- [AUTH_FLOW_GUIDE.md](AUTH_FLOW_GUIDE.md) — Auth flow details
- [amp/backend/api/endpoints.py](amp/backend/api/endpoints.py) — API endpoints
- [amp/backend/database/models.py](amp/backend/database/models.py) — Database models
- [amp/backend/config.py](amp/backend/config.py) — Configuration

---

## Implementation Status

### ✅ Phase 1: Backend Core

| Component | File | Status |
|-----------|------|--------|
| FastAPI Server | `api/server.py` | ✅ CORS enabled |
| API Endpoints | `api/endpoints.py` | ✅ 12 endpoints |
| Database Models | `database/models.py` | ✅ 10 tables |
| Database Sessions | `database/session.py` | ✅ userdb + playdb |
| Configuration | `config.py` | ✅ Pydantic Settings |
| Logging | `utils/logger.py` | ✅ File + console |
| Main Entry | `main.py` | ✅ Server runner |
| Tests | `tests/` | ✅ 20 tests |

### ✅ Phase 2: YouTube Integration

| Component | File | Status |
|-----------|------|--------|
| YouTube Service | `services/youtube.py` | ✅ Search, metadata (28 tests) |
| Auth Service | `services/auth.py` | ✅ Cookie-based, single source of truth |
| Streaming Service | `services/streaming.py` | ✅ yt-dlp, chunk caching (25 tests) |
| Auth Routes | `api/auth_routes.py` | status, cookies, cookie-header, import-browser, open-signin, logout |
| WSL2 Detection | `app/src-tauri/src/wsl_detect.rs` | Auto-detect Windows host IP |
| Build Script | `app/scripts/build-windows-exe.sh` | Clean Windows .exe from WSL2 |
| Auth Tests | `tests/test_ytm_auth.py` | ✅ 11 tests |
| Web Interface | `app/src/` | ✅ React + Vite (port 1420) |
| Auth Hook | `app/src/useYouTubeAuth.ts` | ✅ React auth state |
| Tauri Sign-in | `app/src-tauri/src/youtube_login.rs` | ✅ Google sign-in window |
| Tauri Structure | `app/src-tauri/` | ✅ Fixed for Tauri 2.x |

### ✅ Phase 3: Core Playback System

| Component | File | Status |
|-----------|------|--------|
| Chunk Caching | `services/streaming.py` | ✅ LRU eviction, size monitoring, parallel downloads, pre-fetching |
| Streaming Endpoints | `api/endpoints.py` | ✅ 10 new endpoints with range support, session management |
| Playback State | `services/streaming.py` | ✅ Position tracking, history logging, resume |
| Buffer-Ahead | `services/streaming.py` | ✅ Pre-download chunks, adaptive buffer, seamless transitions |
| Playback UI | `app/src/App.tsx` | ✅ Search bar, play buttons, playback view with chunk visualization |
| Chunk Visualization | `app/src/index.css` | ✅ Color-coded chunk status display |

### ⏳ Pending

| Phase | Priority | Status | Next Action |
|-------|----------|--------|-------------|
| 4: Frontend Buffering | High | ⏳ **NEXT** | Web Audio API implementation |
| 5: Real-Time Fetching | Medium | ⏳ | Buffer-ahead logic |
| 6: Playback Frontend | Medium | ⏳ | React playback UI |
| 7: Library Frontend | Medium | ⏳ | Search/browse UI |
| 8: Tauri Desktop | Medium | ⏳ | Package desktop app |
| 9: Android | Low | ⏳ | Mobile support |
| 10: Polish | Low | ⏳ | Error handling, optimization |

---

## Phase 3: Core Playback System (COMPLETED)

**Objective**: Chunk-based audio streaming and caching.

### Implemented Features

| Task | File | Actions |
|------|------|---------|
| Chunk Caching | `services/streaming.py` | ✅ LRU eviction, size monitoring, parallel downloads, pre-fetching |
| Streaming Endpoints | `api/endpoints.py` | ✅ `GET /api/stream/{song_id}/chunks`, `GET /api/stream/{song_id}/chunk/{chunk_index}`, `POST /api/stream/{song_id}/play`, pause/resume/stop, position, playback-state, buffer |
| Playback State | `services/streaming.py` | ✅ Position tracking, history logging, resume, playback session management |
| Buffer-Ahead | `services/streaming.py` | ✅ Pre-download chunks based on playback position, adaptive buffer management |

### Phase 3 Checklist
- [x] Chunk caching system implemented (LRU eviction, size monitoring, parallel downloads, pre-fetching)
- [x] Streaming endpoints working (10 new endpoints)
- [x] Playback state management working (PlaybackSession class)
- [x] Buffer-ahead logic implemented (DownloadManager with priority queue)
- [x] All existing tests still pass
- [x] New tests added for streaming (53 total tests in test_streaming.py, 116 total)
- [x] AGENTS.md updated with Phase 3 completion
- [x] Frontend debug interface with search bar, play buttons, chunk visualization

### Frontend Features Added
- [x] Search bar on top of liked songs list
- [x] Play button on each video entry
- [x] Playback view with debug interface
- [x] Simple player with play/pause and progress bar
- [x] Chunk visualization with colors (grey=not downloaded, green=downloaded, yellow=downloading, red=error)
- [x] Current chunk highlighted with black border
- [x] Audio playback support via backend streaming

---

## Commands

```bash
# Activate venv (Windows)
activate.bat          # CMD
./activate.ps1        # PowerShell

# Backend
python amp/backend/main.py           # Run server (port 8000)
python amp/backend/main.py --reload  # Auto-reload

# Tests
cd amp && ../venv/Scripts/python.exe -m pytest backend/tests/ -v

# Frontend
cd app && npm run dev               # Dev server (port 1420)
cd app && npm run tauri:dev         # Tauri desktop (needs Rust build tools)

# Auth (browser import)
curl -X POST http://localhost:8000/api/auth/import-browser \
  -H "Content-Type: application/json" -d '{"browser": "firefox"}'

# Build Windows .exe from WSL2
bash app/scripts/build-windows-exe.sh    # Output: build/windows/AMP.exe
```

---

## Key Paths

```
AMP/
├── amp/backend/
│   ├── api/
│   │   ├── endpoints.py       # Main API routes (now includes streaming endpoints)
│   │   └── auth_routes.py     # Auth routes
│   ├── database/
│   │   ├── models.py          # SQLAlchemy models
│   │   └── session.py         # DB sessions
│   ├── services/
│   │   ├── youtube.py         # YouTube Music API
│   │   ├── auth.py            # Cookie-based auth
│   │   └── streaming.py       # Audio streaming (enhanced with Phase 3 features)
│   ├── config.py              # Settings
│   ├── main.py                # Server entry
│   └── tests/                 # 116 tests
├── app/
│   ├── src/
│   │   ├── App.tsx            # Main component (with Phase 3 UI features)
│   │   ├── index.css          # Styles (with chunk visualization)
│   │   └── useYouTubeAuth.ts  # Auth hook
│   └── src-tauri/             # Tauri desktop (structure ready)
├── app/scripts/
│   └── build-windows-exe.sh   # WSL2 cross-compilation script (npm run build:exe)
├── build/windows/             # Clean release output (AMP.exe + WebView2Loader.dll)
├── dist/                      # Frontend build output (Vite)
└── venv/                      # Python virtual environment
```

## Configuration Values

From `amp/backend/config.py`:
```python
CACHE_DIR = BASE_DIR / ".amp" / "cache"
CHUNKS_DIR = CACHE_DIR / "chunks"
CHUNK_SIZE_SEC = 10
CACHE_MAX_SIZE_MB = 500
BUFFER_AHEAD_SEC = 15
```

## Database Access

```python
from backend.database.session import get_userdb_session, get_playdb_session

db = next(get_userdb_session())
# Use db.query(...)
db.close()
```

---

## Coding Guidelines

1. **Read first, then code** — always read files before editing
2. **Follow existing patterns** — match style and structure
3. **Write tests** — add tests for all new functionality
4. **Update docs** — update READMEs as needed
5. **Commit often** — small, atomic commits
6. **Update AGENTS.md** — always update after completing work

## Common Pitfalls

1. **Database sessions**: Always close or use context manager
2. **Import paths**: Use `from backend.xxx import yyy` (run from `amp/` dir)
3. **Windows paths**: Use `Path` from pathlib
4. **Singleton state**: Clean up global state between tests
5. **Auth state**: Use `get_auth_service()` — never create separate auth instances
6. **Streaming state**: Use `get_streaming_service()` — never create separate streaming instances

## Debugging

- Logs: `.amp/logs/app.log`
- Debug mode: `python amp/backend/main.py --debug`
- API docs: http://localhost:8000/docs
- Test auth: `curl http://localhost:8000/api/auth/status`
- Test streaming: `curl http://localhost:8000/api/stream/info/{song_id}`

---

## After Completing Work

1. **Update AGENTS.md** — mark tasks, update phase, set next steps
2. **Commit** — `git add . && git commit -m "feat: description"`
3. **Test** — `cd amp && ../venv/Scripts/python.exe -m pytest backend/tests/ -v`
4. **Document** — update READMEs if needed

---

## Phase 3 Implementation Notes

### Core Features

1. **Chunk Caching System**: Implemented LRU eviction, size monitoring (500MB max), parallel downloads (4 workers), and pre-fetching based on playback position.

2. **Streaming Endpoints**: Added 10 new endpoints for streaming and playback control:
   - `GET /api/stream/{song_id}/chunks` - Get chunk status for a song
   - `GET /api/stream/{song_id}/chunk/{chunk_index}` - Stream a specific chunk
   - `POST /api/stream/{song_id}/play` - Start playback
   - `POST /api/stream/pause` - Pause playback
   - `POST /api/stream/resume` - Resume playback
   - `POST /api/stream/stop` - Stop playback
   - `POST /api/stream/position` - Update playback position
   - `GET /api/stream/playback-state` - Get current playback state
   - `POST /api/stream/buffer/{song_id}` - Start buffering chunks

3. **Playback State Management**: Implemented `PlaybackSession` class for tracking:
   - Current song ID
   - Current chunk index
   - Position within chunk
   - Playing state (play/pause)
   - Volume
   - Buffer-ahead configuration

4. **Buffer-Ahead Logic**: Implemented `DownloadManager` with:
   - Priority queue for chunk downloads
   - 4 parallel download workers
   - Automatic chunk buffering based on playback position
   - Adaptive buffer management

5. **Chunk Status Tracking**: Real-time tracking of chunk states:
   - `not_downloaded` - Chunk not yet downloaded
   - `downloading` - Chunk currently being downloaded
   - `downloaded` - Chunk successfully downloaded
   - `error` - Chunk download failed

### Frontend Features

1. **Search Bar**: Added search functionality to filter liked songs by title or artist.

2. **Play Buttons**: Each song in the list now has a "Play" button that:
   - Starts playback on the backend
   - Opens the playback view
   - Begins buffering chunks

3. **Playback View**: Debug interface showing:
   - Current song title
   - Play/Pause and Stop buttons
   - Current time / Total duration
   - Progress bar (seekable)
   - Chunk visualization grid
   - Legend explaining chunk colors

4. **Chunk Visualization**: Visual representation of all chunks with:
   - Grey (#9e9e9e) for not downloaded
   - Green (#4caf50) for downloaded
   - Yellow (#ffc107) for currently downloading
   - Red (#f44336) for errors
   - Black border for current chunk

### Testing

- All 92 existing tests continue to pass
- Added 24 new tests for Phase 3 features:
  - ChunkStatus enum tests
  - PlaybackInfo dataclass tests
  - DownloadPriority enum tests
  - ChunkDownloadTask tests
  - PlaybackSession tests
  - StreamingService playback tests
  - StreamingService buffering tests
  - Chunk status visualization tests

---

**Last Updated**: 2026-10-18
**Current Phase**: Phase 3 Complete — Phase 4 (Frontend Buffering) Next
**Tests**: 116/116 passing
