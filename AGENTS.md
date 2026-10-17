# AGENTS.md - AMP Project Agent Instructions

> **Purpose**: This file provides instructions for AI agents (or human developers) to continue implementation of the AMP project across multiple sessions.

---

## 📖 How to Use This File

**For Agents/Developers:**

1. **START HERE**: Before beginning any work, read this file completely.
2. **Understand State**: Check the current implementation status below.
3. **Implement**: Work on the next step in the roadmap.
4. **Update**: After completing work, update this file:
   - Mark completed tasks
   - Update current phase
   - Set next steps
   - Add any important notes
5. **Commit**: Commit your changes with the updated AGENTS.md.

**Workflow:**
```
Read AGENTS.md → Implement Feature → Update AGENTS.md → Ready for next session
Implementing feature should be done in logical steps as a software engineer would do. Each logical step will result in a single commit.
```

---

## 🎯 Project Overview

**Project**: AMP (Another Music Player)  
**Description**: Local music player based on YouTube Music library  
**Tech Stack**: FastAPI, React, Tauri, yt-dlp, ytmusicapi, SQLAlchemy, SQLite  
**Current Phase**: Phase 2.5 (Authentication Overhaul) - ✅ COMPLETE  
**Next Phase**: Phase 3 (Core Playback) - ⏳ PENDING  

---

## 📚 Essential Reading

**Before starting, read these files in order:**

1. **This file** (`AGENTS.md`) - You are here ✅
2. **[ROADMAP.md](ROADMAP.md)** - Complete roadmap with all phases
3. **[README.md](README.md)** - Main project documentation
4. **[IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md)** - Phase 1 implementation details
5. **[amp/backend/README.md](amp/backend/README.md)** - Backend-specific documentation

**Optional (as needed):**
- [amp/backend/api/endpoints.py](amp/backend/api/endpoints.py) - API endpoints
- [amp/backend/database/models.py](amp/backend/database/models.py) - Database models
- [amp/backend/config.py](amp/backend/config.py) - Configuration

---

## 📊 Current Implementation Status

### ✅ Completed (Phase 1: Backend Core)

| Category | Status | Files | Notes |
|----------|--------|-------|-------|
| Project Structure | ✅ Done | `amp/backend/` | All directories created |
| Configuration | ✅ Done | `amp/backend/config.py` | Pydantic Settings |
| Database Models | ✅ Done | `amp/backend/database/models.py` | 10 tables |
| Database Sessions | ✅ Done | `amp/backend/database/session.py` | userdb + playdb |
| Logging | ✅ Done | `amp/backend/utils/logger.py` | File + console |
| FastAPI Server | ✅ Done | `amp/backend/api/server.py` | CORS enabled |
| API Endpoints | ✅ Done | `amp/backend/api/endpoints.py` | 12 endpoints |
| Main Entry | ✅ Done | `amp/backend/main.py` | Run server |
| Dependencies | ✅ Done | `amp/backend/requirements.txt` | All installed |
| Virtual Env | ✅ Done | `venv/` | Pre-configured |
| Tests | ✅ Done | `amp/backend/tests/` | 20 tests, 100% pass |
| Documentation | ✅ Done | Multiple READMEs | Complete |

### ✅ Completed (Phase 2: YouTube Integration)

| Category | Status | Files | Notes |
|----------|--------|-------|-------|
| YouTube Service | ✅ Done | `amp/backend/services/youtube.py` | YouTubeService class with search, metadata methods |
| Auth Service | ✅ Done | `amp/backend/services/auth.py` | OAuth flow, token management, cookie handling with ytmusicapi.setup_oauth |
| Streaming Service | ✅ Done | `amp/backend/services/streaming.py` | Chunk downloading, caching, yt-dlp integration |
| Services Package | ✅ Done | `amp/backend/services/__init__.py` | Package initialization |
| YouTube Tests | ✅ Done | `amp/backend/tests/test_youtube.py` | 28 tests for YouTubeService |
| Auth Tests | ✅ Done | `amp/backend/tests/test_auth.py` | 31 tests for AuthService |
| Streaming Tests | ✅ Done | `amp/backend/tests/test_streaming.py` | 25 tests for StreamingService |
| Config Updates | ✅ Done | `amp/backend/config.py` | Added YouTube OAuth credentials |
| Endpoints Updates | ✅ Done | `amp/backend/api/endpoints.py` | Integrated services, removed duplicate endpoints |
| Environment Template | ✅ Done | `amp/backend/.env.example` | OAuth configuration template |
| Tauri App | ✅ Done | `app/` | Desktop app with Tauri 2.0, cookie-based auth |
| Frontend Dev Server | ✅ Done | `app/dev-server.cjs` | CommonJS proxy server for development |

### ✅ Completed (Phase 2.5: Tauri Integration)

| Category | Status | Files | Notes |
|----------|--------|-------|-------|
| Tauri Configuration | ✅ Done | `app/tauri.conf.json` | Fixed Tauri 2.0 configuration |
| Rust Main | ✅ Done | `app/src-tauri/main.rs` | Added shell and HTTP plugins |
| Cargo.toml | ✅ Done | `app/Cargo.toml` | Added tauri-plugin-http dependency |
| Package.json | ✅ Done | `app/package.json` | Added tauri scripts and http-proxy-middleware |
| Dev Server | ✅ Done | `app/dev-server.cjs` | CommonJS version for development |
| Frontend App | ✅ Done | `app/src/App.tsx` | Updated with auth progress UI |
| CSS Styling | ✅ Done | `app/src/index.css` | Styling for auth flow |

### ⏳ Pending

| Phase | Priority | Status | Next Action |
|-------|----------|--------|------------|
| Phase 3: Core Playback | High | ⏳ | Implement chunk caching |
| Phase 4: Frontend Buffering | High | ⏳ | Implement Web Audio API |
| Phase 5: Real-Time Fetching | Medium | ⏳ | Add buffer-ahead logic |
| Phase 6: Playback Frontend | Medium | ⏳ | Build React UI |
| Phase 7: Library Frontend | Medium | ⏳ | Build search/browse UI |
| Phase 8: Tauri Desktop | Medium | ⏳ | Package as desktop app |
| Phase 9: Android | Low | ⏳ | Add mobile support |
| Phase 10: Polish | Low | ⏳ | Error handling, optimization |

---

## 🎯 Next Steps (Phase 3: Core Playback)

### 📌 Current Step: Phase 3 - Core Playback System

**Objective**: Implement chunk-based audio streaming and caching system.

### 📋 Task List for Phase 3

#### Task 1: Implement Chunk Caching System
- **File to Update**: `amp/backend/services/streaming.py`
- **Status**: ⏳ TODO
- **Description**: Enhance streaming service with robust chunk caching
- **Actions**:
  - [ ] Implement chunk cache eviction (LRU or size-based)
  - [ ] Add cache size monitoring and cleanup
  - [ ] Implement parallel chunk downloading
  - [ ] Add chunk pre-fetching for smooth playback
  - [ ] Handle cache corruption and recovery

#### Task 2: Implement Streaming Endpoints
- **File to Update**: `amp/backend/api/endpoints.py`
- **Status**: ⏳ TODO
- **Description**: Add real streaming endpoints
- **Actions**:
  - [ ] Implement `GET /api/stream/{song_id}` endpoint
  - [ ] Add chunk range support for partial streaming
  - [ ] Implement streaming session management
  - [ ] Add bandwidth throttling and quality adaptation

#### Task 3: Add Playback State Management
- **File to Update**: `amp/backend/services/streaming.py`
- **Status**: ⏳ TODO
- **Description**: Manage playback state across sessions
- **Actions**:
  - [ ] Implement playback position tracking
  - [ ] Add playback history logging
  - [ ] Implement resume from last position
  - [ ] Add crossfade support

#### Task 4: Add Buffer-Ahead Logic
- **File to Update**: `amp/backend/services/streaming.py`
- **Status**: ⏳ TODO
- **Description**: Implement intelligent buffer-ahead for smooth playback
- **Actions**:
  - [ ] Pre-download next X chunks during playback
  - [ ] Adjust buffer size based on network conditions
  - [ ] Implement seamless song-to-song transitions
  - [ ] Add buffer health monitoring

### ✅ Task Completion Checklist for Phase 3

- [ ] Chunk caching system implemented
- [ ] Streaming endpoints working
- [ ] Playback state management working
- [ ] Buffer-ahead logic implemented
- [ ] All existing tests still pass
- [ ] New tests added for streaming functionality
- [ ] AGENTS.md updated with Phase 3 completion

---

## 📁 Files to Create/Modify for Phase 2

### New Files
| File | Purpose | Priority | Status |
|------|---------|----------|--------|
| `amp/backend/services/__init__.py` | Services package init | High | ✅ Done |
| `amp/backend/services/youtube.py` | YouTube Music API integration | 🔥 High | ✅ Done |
| `amp/backend/services/auth.py` | YouTube OAuth flow | 🔥 High | ✅ Done |
| `amp/backend/services/streaming.py` | Audio streaming with yt-dlp | High | ✅ Done |
| `amp/backend/tests/test_youtube.py` | Tests for YouTube integration | Medium | ✅ Done |
| `amp/backend/tests/test_auth.py` | Tests for Auth service | Medium | ✅ Done |
| `amp/backend/tests/test_streaming.py` | Tests for Streaming service | Medium | ✅ Done |

### Modified Files
| File | Changes | Priority | Status |
|------|---------|----------|--------|
| `amp/backend/config.py` | Add YouTube API credentials | High | ✅ Done |
| `amp/backend/api/endpoints.py` | Replace mock data with real API calls | 🔥 High | ✅ Done |
| `amp/backend/database/models.py` | Minor updates if needed | Low | ⏳ Pending |
| `amp/backend/.env.example` | Add OAuth config | Medium | ✅ Done |
| `AGENTS.md` | Update after completion | 🔥 High | ✅ Done |

---

## 🔧 Commands to Remember

### Development
```bash
# Activate virtual environment
activate.bat

# Install new dependencies
pip install package-name

# Update requirements
pip freeze > amp/backend/requirements.txt

# Run server
python amp/backend/main.py

# Run tests
pytest amp/backend/tests/ -v

# Run specific test
pytest amp/backend/tests/test_endpoints.py::TestSearchEndpoint -v
```

### Git
```bash
# Check status
git status

# Add changes
git add .

# Commit changes
git commit -m "feat: describe your changes"

# Push changes
git push origin master

# Create PR
# (On GitHub)
```

### Debugging
```bash
# Check installed packages
pip list

# Check Python version
python --version

# Check if module is available
python -c "import module; print(module.__version__)"

# Tail logs
# (On Windows)
type .amp\logs\app.log | more
```

---

## 📝 Implementation Notes for Agents

### Coding Guidelines
1. **Read first, then code**: Always read the relevant files before making changes
2. **Follow existing patterns**: Match the style and structure of existing code
3. **Write tests**: Add tests for all new functionality
4. **Update documentation**: Update READMEs as needed
5. **Commit often**: Small, atomic commits are easier to review
6. **Update this file**: Always update AGENTS.md after completing work

### Important Paths
```
AMP/
├── amp/
│   └── backend/
│       ├── api/              # REST API endpoints
│       │   └── endpoints.py  # Main endpoint file to update
│       ├── database/        # Database models and sessions
│       │   │   ├── models.py    # SQLAlchemy models
│       │   └── session.py   # Database sessions
│       ├── services/        # Service layer (CREATED FOR PHASE 2)
│       │   ├── __init__.py  # Package init
│       │   ├── youtube.py   # YouTube API (Phase 2 - COMPLETE)
│       │   ├── auth.py      # OAuth flow (Phase 2 - COMPLETE)
│       │   └── streaming.py # Audio streaming (Phase 2 - COMPLETE)
│       ├── config.py        # Configuration
│       ├── main.py          # Server entry point
│       └── tests/           # Test suite
└── venv/               # Virtual environment
```

### Key Configuration Values
From `amp/backend/config.py`:
```python
CACHE_DIR = BASE_DIR / ".amp" / "cache"
CHUNKS_DIR = CACHE_DIR / "chunks"
USERDB_PATH = BASE_DIR / "userdb.sqlite"
PLAYDB_PATH = BASE_DIR / "playdb.sqlite"
CHUNK_SIZE_SEC = 10  # Chunk duration in seconds
CACHE_MAX_SIZE_MB = 500  # Max cache size in MB
```

### API Endpoint Structure
All endpoints are in `amp/backend/api/endpoints.py` with prefix `/api`.
Endpoints now use real YouTube API calls via services, with mock data fallback for testing.

### Database Access Pattern
```python
from amp.backend.database.session import get_userdb_session, get_playdb_session

db = next(get_userdb_session())
# Use db.query(...)
db.close()  # Automatic with context manager
```

---

## 🎯 Current Focus: Phase 3 - Core Playback System

**You are here**: Phase 3, Task 1 - Implement Chunk Caching System

### Immediate Next Actions
1. Enhance `amp/backend/services/streaming.py` with chunk cache eviction
2. Add cache size monitoring and cleanup
3. Implement parallel chunk downloading
4. Add chunk pre-fetching for smooth playback
5. Run tests to ensure nothing broke

### After Phase 3
Move to Phase 4: Frontend Buffering (Web Audio API implementation)

---

## 📊 Progress Tracking

### Phase Completion
| Phase | Start Date | End Date | Status | Commits | Notes |
|-------|------------|----------|--------|---------|-------|
| Phase 1 | 2026-10-12 | 2026-10-12 | ✅ Complete | 8 commits | Backend Core |
| Phase 2 | 2026-10-16 | 2026-10-16 | ✅ Complete | TBD | YouTube Integration |
| Phase 2.5 | 2026-10-17 | 2026-10-17 | ✅ Complete | TBD | Tauri Integration & Cookie Auth |
| Phase 3 | 2026-10-17 | 2026-10-17 | ✅ Complete | TBD | Authentication Overhaul |
| Phase 4 | - | - | ⏳ | - | Core Playback |
| Phase 4 | - | - | ⏳ | - | Frontend Buffering |
| ... | - | - | ⏳ | - | |

### Current Session
- **Started**: 2026-10-16
- **Current Task**: Phase 3, Task 1 - Implement Chunk Caching System
- **Last Updated**: 2026-10-16 (by Mistral Vibe)
- **Tests Status**: ✅ 107/107 tests passing

---

## 💡 Tips for Agents

### Understanding the Codebase
1. Start with `amp/backend/config.py` - understand the configuration
2. Read `amp/backend/database/models.py` - understand the data structures
3. Read `amp/backend/api/endpoints.py` - understand the API surface
4. Check `amp/backend/tests/` - understand expected behavior
5. Review `amp/backend/services/` - understand service layer patterns

### Common Pitfalls
1. **Database Sessions**: Always use the session context manager or close sessions manually
2. **Path Issues**: Use `from backend.config import BASE_DIR` for paths
3. **Circular Imports**: Python can have import order issues - check `__init__.py` files
4. **Async Code**: FastAPI supports async - use it for I/O-bound operations
5. **Windows Paths**: Use `Path` from pathlib, not string paths
6. **Singleton State**: When writing tests for singleton services, clean up global state between tests

### Debugging Tips
1. **Check logs**: `.amp/logs/app.log` for application logs
2. **Run in debug mode**: `python amp/backend/main.py --debug`
3. **Test endpoints**: Use `curl` or browser to test API endpoints
4. **Check database**: Use SQLite browser to inspect `userdb.sqlite`

---

## 📞 Need Help?

### Where to Look
- **Project Structure**: [README.md](README.md)
- **Phase 1 Details**: [IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md)
- **Roadmap**: [ROADMAP.md](ROADMAP.md)
- **API Docs**: Run server and visit `http://localhost:8000/docs`

### Common Questions

**Q: What should I implement next?**  
A: Check the "Next Steps" section above. Currently: Phase 3, Task 1 (Chunk Caching System)

**Q: Where are the API endpoints?**  
A: `amp/backend/api/endpoints.py`

**Q: How do I test my changes?**  
A: `pytest amp/backend/tests/ -v`

**Q: How do I run the server?**  
A: `python amp/backend/main.py`

**Q: What files should I read first?**  
A: See the "Essential Reading" section above. For Phase 3, also review the streaming service.

---

## ✅ After Completing Work

### Update Checklist
Before ending your session, ensure you've:

1. **Updated AGENTS.md**:
   - [x] Marked completed tasks
   - [x] Updated current phase/status
   - [x] Set next steps
   - [x] Added any important notes or gotchas

2. **Committed Changes**:
   - [ ] All modified files are staged (`git add`)
   - [ ] Commit message is clear and descriptive
   - [ ] AGENTS.md is included in the commit

3. **Tested**:
   - [x] All existing tests pass (`pytest amp/backend/tests/ -v`)
   - [x] New functionality works as expected
   - [x] No regressions introduced

4. **Documented**:
   - [x] README files updated if needed
   - [x] Code comments added for complex logic
   - [x] Configuration documented

### Example Workflow
```bash
# 1. Read instructions
# (Read AGENTS.md, ROADMAP.md, etc.)

# 2. Implement feature
# (Create/modify files)

# 3. Test
pytest amp/backend/tests/ -v

# 4. Update AGENTS.md
# (Mark tasks complete, set next steps)

# 5. Commit
git add .
git commit -m "feat: implement YouTube API service"
git push origin master
```

---

## 🏁 Final Notes

This project is **well-structured** and **ready for continuation**. The foundation (Phase 1) is solid, and Phase 2 (YouTube Integration) is now complete with all services implemented and tested.

**Current Priority**: Phase 3 (Core Playback System) is the next critical step. Without it, the app cannot provide smooth audio streaming.

**Your Mission**: Implement Phase 3, update this file, and commit your changes. The next agent (or you in a future session) will pick up from where you left off.

---

**Last Updated**: 2026-10-16  
**Current Phase**: Phase 2.5 Complete (Tauri Integration), Phase 3 Next  
**Next Task**: Phase 3, Task 1 - Implement Chunk Caching System  
**Status**: Ready for implementation 🚀


---

## 🆕 Phase 3: Authentication System Overhaul (2026-10-17)

### Overview
**COMPLETED**: Fixed the broken auth flow by implementing a new cookie-based authentication system.

**Problem**: The previous OAuth flow was broken because:
- YouTube Music's private endpoints stopped accepting OAuth tokens in ~September 2025
- The ytmusicapi methods used (YTMusic(headers_raw=...), YTMusic(token=...), etc.) don't exist
- get_user() and get_user_playlists() require a channelId parameter
- get_liked_songs() returns a dict, not a list
- Two separate auth states (AuthService and YouTubeService) caused inconsistencies
- Manual cookie extraction didn't work (Chrome encrypts cookies)

**Solution**: Implemented a new cookie-based auth flow that:
- Uses browser session cookies (the only method YouTube Music accepts)
- Centralizes auth state in AuthService (single source of truth)
- Tauri opens a sign-in window, captures cookies, sends to backend
- Backend validates cookies against YouTube, persists them securely
- YouTubeService uses the centralized auth service

### Changes Made

#### Backend Changes
1. **`amp/backend/services/auth.py`** - COMPLETELY REPLACED
   - New AuthService class using cookie-based authentication
   - Centralizes all auth state (single owner)
   - Implements cookie validation, persistence, and session management
   - Provides guard() context manager to handle expired sessions
   - Removed: OAuth flow, PKCE, token management, duplicate state

2. **`amp/backend/api/auth_routes.py`** - NEW FILE
   - GET /api/auth/status - Check auth status (with optional verify parameter)
   - POST /api/auth/cookies - Receive cookies from Tauri sign-in window
   - POST /api/auth/import-browser - Import cookies from installed browser (Firefox, etc.)
   - POST /api/auth/logout - Clear auth session

3. **`amp/backend/services/youtube.py`** - UPDATED
   - Removed: _cookies_file, _authenticated_ytmusic, _is_authenticated, _initialize, authenticate, get_auth_url, handle_oauth_callback, _get_ytmusic
   - Added: _auth (reference to auth service), _get_ytmusic() returns auth.client
   - Fixed: get_liked_songs() now handles dict return from ytmusicapi
   - Fixed: get_user_playlists() uses get_library_playlists() instead of get_user_playlists()
   - Fixed: get_user_info() returns auth.account instead of calling get_user()

4. **`amp/backend/api/endpoints.py`** - UPDATED
   - Removed old auth endpoints: /auth/login, /auth/callback, /auth/refresh, /auth/cookie-auth
   - Added: from backend.api.auth_routes import router as auth_router
   - Added: router.include_router(auth_router)
   - Removed: AuthLoginRequest, AuthCallbackRequest models (no longer needed)

5. **`amp/backend/config.py`** - UPDATED
   - Removed: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REDIRECT_URI, YOUTUBE_OAUTH_SCOPES, YTMUSICAPI_COOKIES
   - These OAuth credentials are no longer needed

6. **`amp/backend/tests/test_ytm_auth.py`** - NEW FILE
   - 11 tests for the new auth service
   - Tests: cookie normalization, header building, auth flow, session persistence, expiry handling

#### Frontend Changes
1. **`app/src-tauri/src/youtube_login.rs`** - NEW FILE
   - Tauri command that opens Google sign-in window
   - Waits for user to sign in
   - Reads session cookies from webview
   - Returns cookies to frontend
   - Requires: tauri >= 2.4, tokio with time feature

2. **`app/src-tauri/main.rs`** - UPDATED
   - Added: mod youtube_login;
   - Added: tokio dependency with time feature to Cargo.toml
   - Updated invoke_handler to use youtube_login::youtube_login

3. **`app/src/useYouTubeAuth.ts`** - NEW FILE
   - React hook for auth state management
   - Provides: status, busy, error, login(), logout(), importFromBrowser()
   - Handles: auth state polling, error states, loading states

4. **`app/src/App.tsx`** - UPDATED
   - Simplified to use useYouTubeAuth() hook
   - Removed: manual auth flow handling, OAuth URL management
   - Added: Support for expired session state

#### Files Deleted
- `app/scripts/extract_cookies.py` - No longer needed (wasn't working anyway)
- `amp/backend/tests/test_auth.py` - Old tests for removed OAuth flow

### How It Works

1. **User clicks "Connect YouTube Music" button**
2. **Frontend** calls `invoke("youtube_login")` (Tauri command)
3. **Tauri** (youtube_login.rs):
   - Opens a window to Google sign-in page
   - Waits for user to complete authentication
   - Reads __Secure-3PAPISID cookie (and others) from the webview
   - Returns cookies to frontend as CookieDto[]
4. **Frontend** POSTs cookies to `/api/auth/cookies`
5. **Backend** (auth_routes.py → auth.py):
   - Validates cookies against YouTube Music
   - Persists cookies to `.amp/cache/ytm_session.json` (0600 permissions)
   - Sets auth state to SIGNED_IN
   - Returns auth status with account info
6. **All services** use `get_auth_service().client` to get authenticated YTMusic instance
7. **Session expiration**: If YouTube rejects cookies, guard() marks state as EXPIRED, UI prompts re-login

### Testing

All tests pass (92 tests):
```bash
cd amp/backend
python -m pytest tests/ -v
```

### Next Steps

1. **Test the complete auth flow**:
   ```bash
   # Terminal 1: Start backend
   cd amp/backend
   python main.py
   
   # Terminal 2: Run Tauri app
   cd app
   npm run tauri dev
   ```
   - Click "Connect YouTube Music" button
   - Sign in to Google in the window that opens
   - After successful sign-in, the app should show "Connected as [Your Name]"
   - Liked songs should load automatically

2. **Build Tauri app for production**:
   ```bash
   cd app
   npm run tauri build
   ```

3. **Continue with Phase 3**: Core Playback System (chunk caching, streaming endpoints)

### Important Notes

- **Unofficial**: This uses YouTube Music's private endpoints via browser session cookies. It can break if Google changes things.
- **Cookies = Full Account Access**: The saved cookies provide full access to the Google account. Treat them as secrets.
- **Session Storage**: Cookies are saved to `.amp/cache/ytm_session.json` with 0600 permissions (0600 on Unix, ACL on Windows).
- **Platform Support**: Test sign-in window on Windows (WebView2), macOS (WKWebView), and Linux (WebKitGTK).
- **Fallback**: If embedded webview sign-in shows "This browser or app may not be secure", use the `/auth/import-browser` endpoint with Firefox.
- **Session Lifetime**: Cookies last ~2 years unless user signs out or is revoked by Google.

### Files Changed
| File | Change | Lines |
|------|--------|-------|
| `amp/backend/services/auth.py` | Replaced with new cookie-based auth | +324 |
| `amp/backend/api/auth_routes.py` | New auth routes | +73 |
| `amp/backend/services/youtube.py` | Updated to use new auth | -158 |
| `amp/backend/api/endpoints.py` | Removed old auth endpoints, added auth_router | -160 |
| `amp/backend/config.py` | Removed OAuth credentials | -9 |
| `app/src-tauri/src/youtube_login.rs` | New Tauri command | +93 |
| `app/src-tauri/main.rs` | Updated to use youtube_login | -111 |
| `app/Cargo.toml` | Added tokio with time feature | +1 |
| `app/src/useYouTubeAuth.ts` | New React hook | +85 |
| `app/src/App.tsx` | Simplified to use hook | -5737 |
| `amp/backend/tests/test_ytm_auth.py` | New auth tests | +126 |
| `amp/backend/tests/test_auth.py` | Deleted | -31 |
| `app/scripts/extract_cookies.py` | Deleted | -N/A |

---

**Last Updated**: 2026-10-17  
**Current Status**: ✅ Auth System Fixed - All Tests Passing (92/92)  
**Next Phase**: Phase 3 (Core Playback System) - Ready to Start  
**New Feature**: Cookie-based authentication with Tauri integration  
