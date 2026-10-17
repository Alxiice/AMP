# AMP Roadmap

> **See Also**: For complete project details, refer to [README.md](README.md)  
> **Current Phase**: Phase 2.6 (Web Interface Foundation) - ✅ COMPLETE  
> **Next Phase**: Phase 3 (Core Playback System) - ⏳ READY TO START

---

## 🎯 Phases Overview

The AMP project is divided into **12 logical phases** to progressively build a fully-featured music player.

| Phase | Name | Status | Description |
|-------|------|--------|-------------|
| 1 | Backend Core | ✅ **DONE** | FastAPI server, database schema, basic endpoints |
| 2 | YouTube Integration | ✅ **DONE** | ytmusicapi integration, streaming service |
| 2.5 | Authentication Overhaul | ✅ **DONE** | Cookie-based auth system (replaced broken OAuth) |
| 2.6 | Web Interface Foundation | ✅ **DONE** | React frontend with auth UI, web-based testing |
| 3 | Core Playback System | ⏳ **NEXT** | Chunk cache, streaming endpoint, basic player |
| 4 | Frontend Buffering | ⏳ | Web Audio API integration, playback controls |
| 5 | Real-Time Chunk Fetching | ⏳ | Automatic chunk fetching during playback |
| 6 | Playback Frontend | ⏳ | React UI for playback controls |
| 7 | Library Management Frontend | ⏳ | Search UI, library browsing |
| 8 | Tauri Desktop App | ⏳ | Desktop packaging with Tauri |
| 9 | Android Support | ⏳ | Tauri 2.0 mobile support |
| 10 | Testing & Polish | ⏳ | Error handling, performance optimization |

---

## 📋 Detailed Roadmap

### Phase 1: Backend Core ✅ COMPLETE

**Objective**: Establish the foundation with FastAPI, database, and basic endpoints.

#### Tasks
- ✅ FastAPI server setup with Uvicorn
- ✅ SQLite database initialization with SQLAlchemy
- ✅ Base models for `songs`, `playlists`, `queues`
- ✅ Configuration management (Pydantic Settings)
- ✅ Logging setup
- ✅ Virtual environment with dependencies
- ✅ Comprehensive test suite (20 tests)

#### Deliverables
- Running FastAPI server with API docs at `/docs`
- SQLite databases (`userdb.sqlite`, `playdb.sqlite`) initialized
- 12 REST API endpoints (health, search, library, queue, playback)
- All tests passing (100% pass rate)

#### Verification
```bash
# Server should start
python amp/backend/main.py

# All tests should pass
pytest amp/backend/tests/ -v

# API should be accessible
curl http://localhost:8000/api/health
```

---

### Phase 2: YouTube Integration ✅ COMPLETE

**Objective**: Integrate YouTube Music API for real data.

#### Tasks
- ✅ `ytmusicapi` integration for metadata
  - ✅ Search functionality (songs, artists, albums, playlists)
  - ✅ Song metadata fetching (title, artist, album, duration, thumbnail)
  - ✅ Artist info fetching (bio, top tracks, albums)
  - ✅ Album info fetching (tracks, artwork)
  - ✅ Playlist info fetching (tracks, owner)
- ✅ `yt-dlp` integration for audio
  - ✅ Audio streaming from YouTube
  - ✅ Chunk downloading (configurable size: 10s by default)
  - ✅ Quality/format selection (MP3, 192kbps by default)
- ✅ YouTubeService class with 28 tests
- ✅ StreamingService class with 25 tests

#### Files Created
- `amp/backend/services/youtube.py` - YouTube API integration
- `amp/backend/services/streaming.py` - Audio streaming with yt-dlp
- `amp/backend/tests/test_youtube.py` - 28 tests
- `amp/backend/tests/test_streaming.py` - 25 tests

#### Verification
```bash
# Search should return real YouTube results
curl "http://localhost:8000/api/search?q=test"

# Song metadata should be real
curl http://localhost:8000/api/song/dQw4w9WgXcQ
```

---

### Phase 2.5: Authentication Overhaul ✅ COMPLETE (2026-10-17)

**Objective**: Replace the broken OAuth-based authentication with a working cookie-based system.

**Background**: YouTube Music's private endpoints stopped accepting OAuth tokens in ~September 2025. The previous OAuth flow was completely broken.

#### Tasks
- ✅ New cookie-based `AuthService` (replaced `auth.py`)
  - ✅ Single source of truth for auth state
  - ✅ Cookie validation against YouTube
  - ✅ Secure session persistence (0600 permissions)
  - ✅ Session expiration detection (`guard()` context manager)
- ✅ New auth API routes (`auth_routes.py`)
  - ✅ `GET /api/auth/status` - Check auth status
  - ✅ `POST /api/auth/cookies` - Receive cookies from Tauri
  - ✅ `POST /api/auth/import-browser` - Import from installed browser
  - ✅ `POST /api/auth/logout` - Clear session
- ✅ Updated `YouTubeService` to use centralized auth
- ✅ Fixed broken ytmusicapi method calls
  - ✅ `get_liked_songs()` now handles dict return
  - ✅ `get_user_playlists()` uses `get_library_playlists()`
  - ✅ `get_user_info()` returns `auth.account`
- ✅ New Tauri command (`youtube_login.rs`)
  - ✅ Opens Google sign-in window
  - ✅ Captures cookies from webview
  - ✅ Returns cookies to frontend
- ✅ New React hook (`useYouTubeAuth.ts`)
- ✅ 11 new tests for auth service
- ✅ Removed OAuth credentials from config
- ✅ Deleted broken files (`extract_cookies.py`, old tests)

#### Files Created/Modified
- **Created**: `amp/backend/api/auth_routes.py`
- **Replaced**: `amp/backend/services/auth.py` (complete rewrite)
- **Modified**: `amp/backend/services/youtube.py`
- **Modified**: `amp/backend/api/endpoints.py`
- **Modified**: `amp/backend/config.py`
- **Created**: `app/src-tauri/src/youtube_login.rs`
- **Created**: `app/src/useYouTubeAuth.ts`
- **Modified**: `app/src/App.tsx`
- **Modified**: `app/src-tauri/main.rs`
- **Modified**: `app/Cargo.toml`
- **Created**: `amp/backend/tests/test_ytm_auth.py`
- **Deleted**: `amp/backend/tests/test_auth.py`
- **Deleted**: `app/scripts/extract_cookies.py`

#### Verification
```bash
# All tests pass (92 total)
cd amp/backend && python -m pytest tests/ -v

# Auth status endpoint works
curl http://localhost:8000/api/auth/status
# → {"state": "signed_out", "is_authenticated": false, "account": null}
```

---

### Phase 2.6: Web Interface Foundation ✅ COMPLETE (2026-10-17)

**Objective**: Create a working web interface for testing the backend and authentication.

#### Tasks
- ✅ React frontend with Vite dev server
- ✅ `useYouTubeAuth` React hook for auth state management
- ✅ Updated `App.tsx` with auth UI
  - ✅ "Connect YouTube Music" button
  - ✅ Auth status display
  - ✅ Liked songs display
  - ✅ Logout functionality
  - ✅ Expired session handling
- ✅ Web-based testing capability (no Rust/Tauri required)
- ✅ Dev server proxy configuration
- ✅ Fixed project structure for Tauri 2.x
  - ✅ Moved `Cargo.toml` to `src-tauri/`
  - ✅ Moved `tauri.conf.json` to `src-tauri/`
  - ✅ Created `build.rs`
  - ✅ Fixed Vite port configuration
- ✅ Updated CSS styling

#### Files Created/Modified
- **Created**: `app/src/useYouTubeAuth.ts` - React auth hook
- **Modified**: `app/src/App.tsx` - Simplified auth UI
- **Modified**: `app/vite.config.ts` - Fixed port to 1420
- **Modified**: `app/src-tauri/tauri.conf.json` - Tauri 2.x config
- **Modified**: `app/src-tauri/Cargo.toml` - Fixed dependencies
- **Created**: `app/src-tauri/build.rs` - Tauri build script
- **Modified**: `app/src-tauri/src/main.rs` - Simplified for new auth

#### How to Test (Web Interface)
```bash
# Terminal 1: Start backend
cd amp/backend
python main.py

# Terminal 2: Start frontend
cd app
npm run dev
```

Then open **http://localhost:1420** in your browser.

#### Verification
- ✅ Frontend loads at http://localhost:1420
- ✅ "Connect YouTube Music" button appears
- ✅ Auth status polling works
- ✅ Backend API integration works
- ✅ All 92 tests pass

---

### Phase 3: Core Playback System ⏳ NEXT

**Objective**: Implement audio chunk caching and basic playback.

#### Tasks
- [ ] Chunk cache manager
  - [ ] Filesystem storage in `.amp/cache/chunks/`
  - [ ] Metadata tracking in SQLite (`cached_chunks` table)
  - [ ] LRU cleanup when cache exceeds limit (500MB by default)
- [ ] FastAPI streaming endpoint
  - [ ] `GET /api/stream/{song_id}` for chunk streaming
  - [ ] Range requests support for seeking
- [ ] Basic playback manager
  - [ ] Chunk fetching on demand
  - [ ] Pre-fetching next chunks
  - [ ] Playback position tracking

#### Files to Modify
- `amp/backend/services/streaming.py` - Enhance with cache management
- `amp/backend/utils/cache.py` (NEW) - Cache management
- `amp/backend/api/endpoints.py` - Add streaming endpoint
- `amp/backend/database/models.py` - Ensure `cached_chunks` table is complete

#### Verification
```bash
# Streaming endpoint should work
curl -I http://localhost:8000/api/stream/dQw4w9WgXcQ

# Chunks should be cached
ls .amp/cache/chunks/
```

---

### Phase 4: Frontend Buffering ⏳

**Objective**: Implement Web Audio API for client-side playback.

#### Tasks
- [ ] Web Audio API integration
  - [ ] Audio context setup
  - [ ] Buffer management
  - [ ] Playback position tracking
- [ ] Playback controls
  - [ ] Play/pause
  - [ ] Next/previous track
  - [ ] Seek
  - [ ] Volume control
  - [ ] EQ (basic implementation)
- [ ] Backend communication
  - [ ] Fetch chunks via `/api/stream/{song_id}`
  - [ ] Update playback position via `/api/playback/position`

#### Files to Create
- `app/src/services/audio.ts` (NEW) - Web Audio API wrapper
- `app/src/hooks/usePlayback.ts` (NEW) - Playback state hook
- `app/src/hooks/useQueue.ts` (NEW) - Queue management hook

#### Verification
```bash
# Frontend should be able to:
# 1. Load a queue
# 2. Start playback
# 3. Play audio without gaps
# 4. Control playback (play/pause, next, previous, seek)
```

---

### Phase 5: Real-Time Chunk Fetching ⏳

**Objective**: Automatic chunk fetching during playback for seamless streaming.

#### Tasks
- [ ] Buffer-ahead logic
  - [ ] Maintain minimum 10-15 seconds of buffer
  - [ ] Pre-fetch chunks as playback progresses
- [ ] Error handling
  - [ ] Retry failed chunk fetches
  - [ ] Fallback to lower quality if needed
  - [ ] Graceful degradation on network issues
- [ ] Buffer monitoring
  - [ ] Warn when buffer is low
  - [ ] Pause if buffer is exhausted

#### Files to Modify
- `app/src/services/audio.ts` - Add buffer-ahead logic
- `amp/backend/api/endpoints.py` - Add buffer status endpoint

#### Verification
```bash
# Playback should continue seamlessly
# even with slow network (simulate with throttling)
```

---

### Phase 6: Playback Frontend ⏳

**Objective**: Build React UI for playback controls.

#### Tasks
- [ ] React UI components
  - [ ] Playback controls (play/pause, next, previous)
  - [ ] Progress bar with seek
  - [ ] Volume slider
  - [ ] EQ controls
  - [ ] Now-playing panel (title, artist, album art)
- [ ] Queue visualization
  - [ ] Scrollable queue list
  - [ ] Current track highlighted
  - [ ] Click to select track

#### Files to Create
- `app/src/components/PlaybackControls.tsx` (NEW)
- `app/src/components/ProgressBar.tsx` (NEW)
- `app/src/components/NowPlaying.tsx` (NEW)
- `app/src/components/QueueView.tsx` (NEW)

#### Verification
```bash
# UI should display:
# - Current playing track
# - Playback controls (all functional)
# - Queue with all tracks
# - Progress bar that updates
```

---

### Phase 7: Library Management Frontend ⏳

**Objective**: Build UI for browsing and searching the library.

#### Tasks
- [ ] Library browsing UI
  - [ ] Search bar
  - [ ] Results display (songs, artists, albums, playlists)
  - [ ] Detail pages for each item type
- [ ] Queue building
  - [ ] Click song to add to queue
  - [ ] Click playlist to load queue
  - [ ] Drag-and-drop queue management

#### Files to Create
- `app/src/components/SearchBar.tsx` (NEW)
- `app/src/components/SearchResults.tsx` (NEW)
- `app/src/components/ArtistView.tsx` (NEW)
- `app/src/components/AlbumView.tsx` (NEW)
- `app/src/components/PlaylistView.tsx` (NEW)

#### Verification
```bash
# Users should be able to:
# 1. Search the library
# 2. Browse results
# 3. View item details
# 4. Add items to queue
```

---

### Phase 8: Tauri Desktop App ⏳

**Objective**: Package the app as a desktop application.

#### Tasks
- [ ] Tauri configuration (partially done in Phase 2.6)
- [ ] Auto-start backend
  - [ ] Start FastAPI server on app launch
  - [ ] Manage server lifecycle
- [ ] Desktop integration
  - [ ] System tray icon
  - [ ] Global hotkeys (play/pause, next, previous)
- [ ] Fix Rust compilation (requires Visual Studio Build Tools)

#### Prerequisites
- Visual Studio Build Tools with C++ workload (Windows)
- Or use WSL2 with GNU toolchain

#### Files to Modify
- `app/src-tauri/src/main.rs` - Add backend lifecycle management
- `app/src-tauri/tauri.conf.json` - Desktop configuration

#### Verification
```bash
# Desktop app should:
# 1. Install and run
# 2. Start backend automatically
# 3. Open frontend in native window
# 4. Work like web version
```

---

### Phase 9: Android Support ⏳

**Objective**: Add mobile support using Tauri 2.0.

#### Tasks
- [ ] Tauri mobile configuration
- [ ] Backend compatibility
  - [ ] Ensure all endpoints work on mobile
  - [ ] Handle mobile network constraints
- [ ] Mobile UI adjustments
  - [ ] Responsive design
  - [ ] Touch-friendly controls

#### Files to Modify
- `app/src-tauri/tauri.conf.json` - Add mobile configuration
- `app/src/styles/` - Mobile-responsive CSS

#### Verification
```bash
# APK should:
# 1. Install on Android device
# 2. Open and work
# 3. Have functional UI
# 4. Play audio
```

---

### Phase 10: Testing & Polish ⏳

**Objective**: Final polish, error handling, and performance optimization.

#### Tasks
- [ ] Error handling
  - [ ] Network error recovery
  - [ ] YouTube API error handling
  - [ ] User-friendly error messages
- [ ] Cross-platform testing
  - [ ] Windows testing
  - [ ] Linux testing
  - [ ] Android testing (when Phase 9 is done)
- [ ] Performance optimization
  - [ ] Chunk size tuning
  - [ ] Buffer size tuning
  - [ ] Caching strategy optimization
- [ ] UI/UX polish
  - [ ] Animations
  - [ ] Themes (light/dark mode)
  - [ ] Accessibility

#### Verification
```bash
# All error cases should be handled gracefully
# Performance should be smooth
# UI should be polished
```

---

## 🎯 Current Status

| Phase | Status | Progress |
|-------|--------|----------|
| Phase 1: Backend Core | ✅ **COMPLETE** | 100% |
| Phase 2: YouTube Integration | ✅ **COMPLETE** | 100% |
| Phase 2.5: Authentication Overhaul | ✅ **COMPLETE** | 100% |
| Phase 2.6: Web Interface Foundation | ✅ **COMPLETE** | 100% |
| Phase 3: Core Playback System | ⏳ **NEXT** | 0% |
| Phase 4: Frontend Buffering | ⏳ | 0% |
| Phase 5: Real-Time Chunk Fetching | ⏳ | 0% |
| Phase 6: Playback Frontend | ⏳ | 0% |
| Phase 7: Library Management Frontend | ⏳ | 0% |
| Phase 8: Tauri Desktop App | ⏳ | 0% |
| Phase 9: Android Support | ⏳ | 0% |
| Phase 10: Testing & Polish | ⏳ | 0% |

**Overall Progress**: 33% (4 of 12 phases complete)

---

## 📅 Timeline (Estimated)

| Phase | Complexity | Estimated Time | Status |
|-------|------------|----------------|--------|
| Phase 1 | ✅ Done | 1 day | Complete |
| Phase 2 | ✅ Done | 1-2 days | Complete |
| Phase 2.5 | ✅ Done | 0.5 days | Complete |
| Phase 2.6 | ✅ Done | 0.5 days | Complete |
| Phase 3 | Medium | 1 day | Next |
| Phase 4 | Medium | 1-2 days | Pending |
| Phase 5 | Low | 0.5 days | Pending |
| Phase 6 | Medium | 1 day | Pending |
| Phase 7 | Medium | 1-2 days | Pending |
| Phase 8 | Medium | 1 day | Pending |
| Phase 9 | Medium | 1 day | Pending |
| Phase 10 | Low | 0.5-1 days | Pending |
| **Total** | | **8-12 days** | |

---

## 🏆 Milestones

### MVP 1: Backend + Basic Playback
- **Phases**: 1, 2, 2.5, 2.6, 3, 4
- **Status**: 67% complete (Phases 1-2.6 done)
- **Estimated**: 2-3 more days
- **Capabilities**: Backend with real YouTube data + web interface + basic playback

### MVP 2: Full Desktop App
- **Phases**: 1-8
- **Status**: 50% complete
- **Estimated**: 5-7 more days
- **Capabilities**: Full desktop app with library browsing and playback

### MVP 3: Cross-Platform (Desktop + Mobile)
- **Phases**: 1-9
- **Status**: 42% complete
- **Estimated**: 6-8 more days
- **Capabilities**: Desktop + Android app

### Final: Production Ready
- **Phases**: 1-10
- **Status**: 33% complete
- **Estimated**: 8-12 more days
- **Capabilities**: Full-featured, polished, production-ready app

---

## 📚 See Also

- [README.md](README.md) - Main project documentation
- [AGENTS.md](AGENTS.md) - Agent instructions and current status
- [IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md) - Phase 1 implementation details
- [IMPLEMENTATION_NOTES_PHASE_2.5.md](IMPLEMENTATION_NOTES_PHASE_2.5.md) - Auth Overhaul details
- [IMPLEMENTATION_NOTES_PHASE_2.6.md](IMPLEMENTATION_NOTES_PHASE_2.6.md) - Web Interface details
- [amp/backend/README.md](amp/backend/README.md) - Backend-specific guide
- [app/README.md](app/README.md) - Frontend app guide
- [QUICK_START.md](QUICK_START.md) - Quick start guide
- [AUTH_FLOW_GUIDE.md](AUTH_FLOW_GUIDE.md) - Authentication flow guide
