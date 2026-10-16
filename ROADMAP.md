# AMP Roadmap

> **See Also**: For complete project details, refer to [README.md](README.md)  
> **Current Phase**: Phase 2 (YouTube Integration) - ✅ COMPLETE

---

## 🎯 Phases Overview

The AMP project is divided into **10 logical phases** to progressively build a fully-featured music player.

| Phase | Name | Status | Description |
|-------|------|--------|-------------|
| 1 | Backend Core | ✅ **DONE** | FastAPI server, database schema, basic endpoints |
| 2 | YouTube Integration | ⏳ **NEXT** | yt-dlp/ytmusicapi integration, authentication |
| 3 | Core Playback System | ⏳ | Chunk cache, streaming endpoint, basic player |
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
- ✅ YouTube OAuth flow
  - ✅ Authentication with YouTube
  - ✅ Access to user playlists
  - ✅ Access to liked songs
  - ✅ Token storage and refresh

#### Files to Modify
- `amp/backend/services/youtube.py` (NEW) - YouTube API integration
- `amp/backend/services/auth.py` (NEW) - OAuth flow
- `amp/backend/api/endpoints.py` - Replace mock data with real API calls
- `amp/backend/config.py` - Add YouTube API credentials
- `amp/backend/.env.example` - Add OAuth configuration

#### Dependencies
- ytmusicapi (already installed)
- yt-dlp (already installed)

#### Verification
```bash
# Search should return real YouTube results
curl "http://localhost:8000/api/search?q=test"

# Song metadata should be real
curl http://localhost:8000/api/song/dQw4w9WgXcQ
```

---

### Phase 3: Core Playback System ⏳

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
- `amp/backend/services/streaming.py` (NEW) - Chunk streaming logic
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
- `frontend/src/services/audio.js` (NEW) - Web Audio API wrapper
- `frontend/src/hooks/usePlayback.js` (NEW) - Playback state hook
- `frontend/src/hooks/useQueue.js` (NEW) - Queue management hook

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
- `frontend/src/services/audio.js` - Add buffer-ahead logic
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
- `frontend/src/components/PlaybackControls.jsx` (NEW)
- `frontend/src/components/ProgressBar.jsx` (NEW)
- `frontend/src/components/NowPlaying.jsx` (NEW)
- `frontend/src/components/QueueView.jsx` (NEW)

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
- [ ] Authentication UI
  - [ ] YouTube OAuth button
  - [ ] Token management
  - [ ] User profile display
- [ ] Queue building
  - [ ] Click song to add to queue
  - [ ] Click playlist to load queue
  - [ ] Drag-and-drop queue management

#### Files to Create
- `frontend/src/components/SearchBar.jsx` (NEW)
- `frontend/src/components/SearchResults.jsx` (NEW)
- `frontend/src/components/ArtistView.jsx` (NEW)
- `frontend/src/components/AlbumView.jsx` (NEW)
- `frontend/src/components/PlaylistView.jsx` (NEW)
- `frontend/src/components/AuthButton.jsx` (NEW)

#### Verification
```bash
# Users should be able to:
# 1. Search the library
# 2. Browse results
# 3. View item details
# 4. Authenticate with YouTube
# 5. Add items to queue
```

---

### Phase 8: Tauri Desktop App ⏳

**Objective**: Package the app as a desktop application.

#### Tasks
- [ ] Tauri configuration
  - [ ] `tauri.conf.json` setup
  - [ ] Backend + frontend bundling
- [ ] Auto-start backend
  - [ ] Start FastAPI server on app launch
  - [ ] Manage server lifecycle
- [ ] Desktop integration
  - [ ] System tray icon
  - [ ] Global hotkeys (play/pause, next, previous)

#### Files to Create
- `tauri.conf.json` (NEW)
- `frontend/tauri/` (NEW) - Tauri configuration
- `amp/backend/tauri_server.py` (NEW) - Server lifecycle management

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
- `tauri.conf.json` - Add mobile configuration
- `frontend/src/styles/` - Mobile-responsive CSS

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
| Phase 3: Core Playback System | ⏳ | 0% |
| Phase 4: Frontend Buffering | ⏳ | 0% |
| Phase 5: Real-Time Chunk Fetching | ⏳ | 0% |
| Phase 6: Playback Frontend | ⏳ | 0% |
| Phase 7: Library Management Frontend | ⏳ | 0% |
| Phase 8: Tauri Desktop App | ⏳ | 0% |
| Phase 9: Android Support | ⏳ | 0% |
| Phase 10: Testing & Polish | ⏳ | 0% |

**Overall Progress**: 20% (2 of 10 phases complete)

---

## 📅 Timeline (Estimated)

| Phase | Complexity | Estimated Time |
|-------|------------|----------------|
| Phase 1 | ✅ Done | 1 day |
| Phase 2 | ✅ Done | 1-2 days |
| Phase 3 | Medium | 1 day |
| Phase 4 | Medium | 1-2 days |
| Phase 5 | Low | 0.5 days |
| Phase 6 | Medium | 1 day |
| Phase 7 | Medium | 1-2 days |
| Phase 8 | Medium | 1 day |
| Phase 9 | Medium | 1 day |
| Phase 10 | Low | 0.5-1 days |
| **Total** | | **8-12 days** |

---

## 🏆 Milestones

### MVP 1: Backend + Basic Playback
- **Phases**: 1, 2, 3, 4
- **Status**: 20% complete
- **Estimated**: 3-5 days
- **Capabilities**: Backend with real YouTube data + basic playback

### MVP 2: Full Desktop App
- **Phases**: 1-8
- **Status**: 20% complete
- **Estimated**: 7-10 days
- **Capabilities**: Full desktop app with library browsing and playback

### MVP 3: Cross-Platform (Desktop + Mobile)
- **Phases**: 1-9
- **Status**: 10% complete
- **Estimated**: 8-11 days
- **Capabilities**: Desktop + Android app

### Final: Production Ready
- **Phases**: 1-10
- **Status**: 10% complete
- **Estimated**: 8-12 days
- **Capabilities**: Full-featured, polished, production-ready app

---

## 📚 See Also

- [README.md](README.md) - Main project documentation
- [IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md) - Phase 1 implementation details
- [amp/backend/README.md](amp/backend/README.md) - Backend-specific guide
- [amp/backend/tests/README.md](amp/backend/tests/README.md) - Testing instructions
