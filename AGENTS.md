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
**Current Phase**: Phase 3 (Core Playback System) — ✅ COMPLETE (fixed 2026-10-19)
**Next Phase**: Phase 4 (Frontend Buffering) — ⏳ READY TO START
**Tests**: 135/135 passing (116 unit + 19 integration)

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

## Phase 3 Fixes (2026-10-19)

### Issues Fixed

1. **Missing StreamingService methods**: The API endpoints called 14 methods that didn't exist on `StreamingService`:
   - `start_playback`, `pause_playback`, `resume_playback`, `stop_playback`
   - `update_playback_position`, `get_current_song_id`, `get_current_chunk_index`
   - `get_playback_state`, `get_streaming_logs`, `get_song_chunks_status`
   - `buffer_chunks_for_song`, `_save_chunk_metadata`, `_save_playback_state`, `_get_total_cache_size`
   - All implemented in `amp/backend/services/streaming.py`

2. **yt-dlp authentication**: YouTube downloads failed with 403 Forbidden. Fixed by:
   - Added `get_cookie_header()` and `get_cookies_dict()` to `AuthService` (`services/auth.py`)
   - Added `_get_yt_dlp_cookie_args()` to `StreamingService` — writes cookies to Netscape-format temp file
   - Added `--cookies <file>` to all yt-dlp commands
   - Added `--js-runtimes node` to all yt-dlp commands (YouTube requires JS runtime for extraction)
   - Fixed `_get_yt_dlp_path()` to prefer venv's yt-dlp (has EJS components installed)

3. **Full song streaming endpoint**: Added `GET /api/stream/{song_id}/audio` for direct playback:
   - Added `download_full_song()` and `get_full_song_path()` to `StreamingService`
   - Downloads complete audio file via yt-dlp for actual playback (byte-range chunks are not independently playable)

4. **Frontend player rewritten** (`app/src/App.tsx`):
   - Click on any liked song to play it immediately
   - Fixed mini-player bar at bottom with: thumbnail, title, artist, play/pause/stop, time display
   - Timeline with chunk visualization: each chunk segment colored by download status
   - Chunk status polled every 2 seconds from `/api/stream/{song_id}/chunks`
   - Audio playback via `/api/stream/{song_id}/audio` endpoint using HTML5 Audio
   - Click on timeline to seek
   - Legend showing chunk status colors

### Integration Tests Added

New file: `amp/backend/tests/test_streaming_integration.py` (19 tests)
- Tests real chunk-by-chunk downloading from YouTube Music (song: dQw4w9WgXcQ)
- Tests: yt-dlp availability, stream info, chunk download (0, 1, multiple), caching, status tracking
- Tests: full song download, playback control (start/pause/resume/stop/position)
- Tests: API endpoints (chunks status, stream info, playback state)
- Marked with `pytest.mark.integration` — run with `-m integration`
- Session fixture manages `ytm_session.json` (copies from `.cookies.json`, cleans up after)

### Test Results

```
135 passed in 48.27s (116 unit + 19 integration)
```

---

## Phase 3 Fixes (2026-10-19, second round)

### Chunk System Fix — HTTP Range requests (true streaming)

**Problem**: The initial fix downloaded the full song then split it with ffmpeg. This defeated the purpose of chunked streaming — users had to wait for the entire song to download before hearing anything.

**Solution**: Download individual byte-range chunks using HTTP Range requests on the direct stream URL. Each chunk is ~10 seconds of audio (~157KB at 160kbps) and downloads independently in ~0.16 seconds.

**How it works**:
1. `get_stream_info()` — gets duration and calculates total chunks (22 chunks for a 3:33 song)
2. `_get_direct_audio_url()` — gets the direct stream URL via yt-dlp (metadata only, cached)
3. `_get_url_content_length()` — gets total stream size via HEAD request (cached)
4. `_get_chunk_byte_range()` — calculates proportional byte ranges:
   `chunk_bytes = total_bytes * (10000ms / duration_ms)` → ~157KB per chunk
5. `_download_byte_range()` — downloads each chunk using `Range: bytes=start-end` header
6. `generate_audio_stream()` — generator that yields chunks sequentially for the audio endpoint

**Key methods** (`amp/backend/services/streaming.py`):
- `download_chunk()` — downloads a single chunk via HTTP Range request (no full download, no ffmpeg)
- `_get_chunk_byte_range()` / `_get_chunk_byte_ranges()` — calculates and caches byte ranges per song
- `_get_stream_url_cached()` / `_get_stream_size_cached()` — caches URL and size to avoid repeated yt-dlp/HEAD calls
- `generate_audio_stream()` — generator yielding chunk data sequentially for streaming playback
- `get_stream_content_type()` — returns `audio/webm` MIME type
- `get_stream_total_bytes()` — returns total stream size for Content-Length header

**Audio endpoint** (`/api/stream/{song_id}/audio`):
- Returns `StreamingResponse` with `generate_audio_stream()` generator
- First chunk downloads on-demand (~0.16s), playback starts immediately
- Subsequent chunks download progressively as the stream progresses
- Content-Type: `audio/webm`, Accept-Ranges: bytes

**Verified with real song** (dQw4w9WgXcQ, 3:33 duration):
```
Stream info: duration=213000ms, total_chunks=22 (3.6s)
Total stream size: 3433755 bytes (3.27 MB)
Chunk 0: 161209 bytes (157.4 KB) in 0.16s
Chunk 1: 161209 bytes (157.4 KB) in 0.16s
Chunk 2: 161209 bytes (157.4 KB) in 0.15s
Each chunk is 4.7% of full stream — real byte ranges, not full copies
```

### Restored Missing Methods

22 methods were accidentally deleted during the chunk fix and restored:
- Chunk metadata: `_save_chunk_metadata`, `get_chunk_data`, `get_chunk_bytes_range`
- Buffering: `buffer_chunks_for_song`, `_cleanup_download_tracking`
- Cache: `cleanup_cache`, `_get_total_cache_size`, `_get_chunks_to_remove`, `_remove_chunks`, `cache_full_song`
- Playback: `start_playback`, `pause_playback`, `resume_playback`, `stop_playback`, `update_playback_position`, `_save_playback_state`, `get_playback_state`
- Status: `get_song_chunks_status`, `get_current_chunk_index`, `get_current_song_id`
- Logging: `get_streaming_logs`, `shutdown`

### Frontend Progress Bar Slider (`app/src/App.tsx`)

- Added invisible `<input type="range">` overlay on the chunk timeline for drag-to-seek
- Added gradient progress fill overlay showing playback position
- Added glowing white position indicator line (3px with box-shadow)
- Added time labels (current / total) below the slider
- Chunk segments now show through the progress fill with reduced opacity for non-current chunks

### Test Fixes

- `test_chunk_status_update_on_download`: Updated to mock `_get_stream_url_cached`, `_get_chunk_byte_range`, and `_download_byte_range` (new Range-request flow)
- `test_auth_status_endpoint`: Accept both authenticated and unauthenticated states (cookies may exist on disk)

### Test Results

```
135 passed in 40.32s
```

---

## Phase 3 Fixes (2026-10-19, third round)

### Content-Length Fallback Chain

**Problem**: Some songs failed with "no content length" because YouTube CDN doesn't always return Content-Length on HEAD requests.

**Solution**: Multi-strategy fallback in `_get_stream_size_cached()`:
1. HTTP HEAD request (fastest)
2. GET with Range bytes=0-0, parse Content-Range header
3. yt-dlp --get-filesize (new `_get_filesize_with_yt_dlp()` method)
4. Estimate from bitrate (160kbps) x duration + 10% overhead

### Seek with Download Re-balancing

**New method**: `seek_to_position(position_ms)` in StreamingService:
- Cancels downloads for chunks before the target position
- Resets their status to not_downloaded
- Removes them from DownloadManager active downloads
- Re-buffers chunks from the new position with buffer-ahead

**New endpoint**: POST /api/stream/seek?position_ms=X

### Frontend: API Monitoring Panel

- Logged fetch wrapper (loggedFetch): intercepts every API call
- Logs: timestamp, method, URL, status code, duration, request body, response preview
- Panel shows: request count, OK/error counts, filter by URL, clear button
- Color-coded: green=2xx, yellow=3xx, red=4xx/5xx/error
- Toggle button in status bar shows error count in red when errors exist
- Keeps last 200 entries

### Frontend: Duration Fix

- Fetches /api/stream/info/{song_id} when song starts if duration unknown
- Listens to audio element loadedmetadata event for actual duration
- Updates currentSong.duration_ms from both sources

### Frontend: Draggable Chunk Bar Cursor

- Range slider with drag-to-preview, release-to-commit
- Visual cursor handle (12px rounded, white with shadow)
- During drag: time display highlights, progress fill follows cursor
- On release: calls POST /api/stream/seek to re-balance downloads
- Backend cancels old chunk downloads, starts new ones from seek position

### .gitignore

- Added tools/ to exclude ffmpeg static builds from repository

### Test Results

```
135 passed in 41.98s
```

---

**Last Updated**: 2026-10-19
**Current Phase**: Phase 3 Complete (fixed) — Phase 4 (Frontend Buffering) Next
**Tests**: 135/135 passing (116 unit + 19 integration)
