# AMP Roadmap

> **Current Phase**: Phase 2 (YouTube Integration) — ✅ COMPLETE
> **Next Phase**: Phase 3 (Core Playback System) — ⏳ READY TO START
> **Tests**: 92/92 passing

---

## Phases Overview

| Phase | Name | Status | Description |
|-------|------|--------|-------------|
| 1 | Backend Core | ✅ **DONE** | FastAPI server, database schema, basic endpoints |
| 2 | YouTube Integration | ✅ **DONE** | ytmusicapi, yt-dlp, cookie-based auth, web interface |
| 3 | Core Playback System | ⏳ **NEXT** | Chunk cache, streaming endpoint, basic player |
| 4 | Frontend Buffering | ⏳ | Web Audio API integration, playback controls |
| 5 | Real-Time Chunk Fetching | ⏳ | Automatic chunk fetching during playback |
| 6 | Playback Frontend | ⏳ | React UI for playback controls |
| 7 | Library Management Frontend | ⏳ | Search UI, library browsing |
| 8 | Tauri Desktop App | ⏳ | Desktop packaging with Tauri |
| 9 | Android Support | ⏳ | Tauri 2.0 mobile support |
| 10 | Testing & Polish | ⏳ | Error handling, performance optimization |

**Overall Progress**: 20% (2 of 10 phases complete)

---

## Phase 1: Backend Core ✅ COMPLETE

**Objective**: Establish the foundation with FastAPI, database, and basic endpoints.

- ✅ FastAPI server with Uvicorn
- ✅ SQLite + SQLAlchemy (10 tables: userdb + playdb)
- ✅ Pydantic Settings configuration
- ✅ Logging (file + console)
- ✅ 12 REST API endpoints
- ✅ 20 tests passing

---

## Phase 2: YouTube Integration ✅ COMPLETE

**Objective**: Integrate YouTube Music for real data, authentication, and a testable web interface.

### YouTube Music API
- ✅ `ytmusicapi` — search, song/artist/album/playlist metadata
- ✅ `yt-dlp` — audio streaming, chunk downloading
- ✅ `YouTubeService` (28 tests) + `StreamingService` (25 tests)
- ✅ All endpoints wired to real services

### Authentication (Cookie-based)
- ✅ Replaced broken OAuth with cookie-based auth (YouTube Music stopped accepting OAuth tokens ~Sept 2025)
- ✅ `AuthService` — single source of truth, session persistence (0600), expiry detection
- ✅ Auth routes: `GET /auth/status`, `POST /auth/cookies`, `POST /auth/import-browser`, `POST /auth/logout`
- ✅ Tauri sign-in window (`youtube_login.rs`) — opens Google login, captures cookies
- ✅ Browser import fallback (Firefox via yt-dlp)
- ✅ 11 new auth tests

### Web Interface
- ✅ React + Vite dev server (http://localhost:1420)
- ✅ `useYouTubeAuth` React hook for auth state
- ✅ Auth UI: connect button, status display, liked songs
- ✅ Fixed Tauri 2.x project structure (ready for desktop build)

**Total tests**: 92 (20 Phase 1 + 53 YouTube/Streaming + 11 Auth + 8 misc)

---

## Phase 3: Core Playback System ⏳ NEXT

**Objective**: Implement audio chunk caching and basic playback.

- [ ] Chunk cache manager (`.amp/cache/chunks/`, LRU cleanup at 500MB)
- [ ] `GET /api/stream/{song_id}` streaming endpoint with range support
- [ ] Playback position tracking + resume
- [ ] Buffer-ahead logic (pre-fetch next chunks)

**Files to modify**: `services/streaming.py`, `api/endpoints.py`, `database/models.py`

---

## Phase 4: Frontend Buffering ⏳

**Objective**: Web Audio API for client-side playback.

- [ ] Audio context + buffer management
- [ ] Play/pause, next/previous, seek, volume, EQ
- [ ] Fetch chunks via `/api/stream/{song_id}`

**Files to create**: `app/src/services/audio.ts`, `app/src/hooks/usePlayback.ts`

---

## Phase 5: Real-Time Chunk Fetching ⏳

**Objective**: Automatic chunk fetching during playback.

- [ ] Buffer-ahead logic (maintain 10-15s buffer)
- [ ] Retry failed fetches, graceful degradation

---

## Phase 6: Playback Frontend ⏳

**Objective**: React UI for playback controls.

- [ ] Playback controls, progress bar, volume, EQ
- [ ] Now-playing panel (title, artist, album art)
- [ ] Queue visualization

**Files to create**: `app/src/components/PlaybackControls.tsx`, `NowPlaying.tsx`, `QueueView.tsx`

---

## Phase 7: Library Management Frontend ⏳

**Objective**: UI for browsing and searching the library.

- [ ] Search bar + results display
- [ ] Artist/album/playlist detail pages
- [ ] Add items to queue

**Files to create**: `app/src/components/SearchBar.tsx`, `SearchResults.tsx`, detail views

---

## Phase 8: Tauri Desktop App ⏳

**Objective**: Package as a desktop application.

- [ ] Auto-start backend on app launch
- [ ] System tray, global hotkeys
- [ ] Fix Rust compilation (requires Visual Studio Build Tools with C++ workload)

---

## Phase 9: Android Support ⏳

**Objective**: Mobile support via Tauri 2.0.

- [ ] Tauri mobile config, responsive UI, touch controls

---

## Phase 10: Testing & Polish ⏳

**Objective**: Production readiness.

- [ ] Error handling, cross-platform testing, performance optimization, UI/UX polish

---

## Milestones

| Milestone | Phases | Status |
|-----------|--------|--------|
| MVP 1: Backend + Basic Playback | 1-4 | 50% (1-2 done) |
| MVP 2: Full Desktop App | 1-8 | 25% |
| MVP 3: Cross-Platform | 1-9 | 22% |
| Production Ready | 1-10 | 20% |

---

## See Also

- [README.md](README.md) — Project overview
- [AGENTS.md](AGENTS.md) — Agent/developer instructions
- [IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md) — Phase implementation details
- [AUTH_FLOW_GUIDE.md](AUTH_FLOW_GUIDE.md) — Authentication documentation
- [amp/backend/README.md](amp/backend/README.md) — Backend guide
- [app/README.md](app/README.md) — Frontend guide
