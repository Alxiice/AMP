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
Read AGENTS.md → Implement Feature → Update AGENTS.md → Commit → Ready for next session
```

---

## 🎯 Project Overview

**Project**: AMP (Another Music Player)  
**Description**: Local music player based on YouTube Music library  
**Tech Stack**: FastAPI, React, Tauri, yt-dlp, ytmusicapi, SQLAlchemy, SQLite  
**Current Phase**: Phase 1 (Backend Core) - ✅ COMPLETE  
**Next Phase**: Phase 2 (YouTube Integration) - ⏳ PENDING

---

## 📚 Essential Reading

**Before starting, read these files in order:**

1. **This file** (`AGENTS.md`) - You are here ✅
2. **[ROADMAP.md](ROADMAP.md)** - Complete roadmap with all phases
3. **[README.md](README.md)** - Main project documentation
4. **[IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md)** - Phase 1 implementation details
5. **[backend/README.md](backend/README.md)** - Backend-specific documentation

**Optional (as needed):**
- [backend/api/endpoints.py](backend/api/endpoints.py) - API endpoints
- [backend/database/models.py](backend/database/models.py) - Database models
- [backend/config.py](backend/config.py) - Configuration

---

## 📊 Current Implementation Status

### ✅ Completed (Phase 1: Backend Core)

| Category | Status | Files | Notes |
|----------|--------|-------|-------|
| Project Structure | ✅ Done | `backend/` | All directories created |
| Configuration | ✅ Done | `backend/config.py` | Pydantic Settings |
| Database Models | ✅ Done | `backend/database/models.py` | 10 tables |
| Database Sessions | ✅ Done | `backend/database/session.py` | userdb + playdb |
| Logging | ✅ Done | `backend/utils/logger.py` | File + console |
| FastAPI Server | ✅ Done | `backend/api/server.py` | CORS enabled |
| API Endpoints | ✅ Done | `backend/api/endpoints.py` | 12 endpoints |
| Main Entry | ✅ Done | `backend/main.py` | Run server |
| Dependencies | ✅ Done | `backend/requirements.txt` | All installed |
| Virtual Env | ✅ Done | `venv/` | Pre-configured |
| Tests | ✅ Done | `backend/tests/` | 20 tests, 100% pass |
| Documentation | ✅ Done | Multiple READMEs | Complete |

### ⏳ Pending

| Phase | Priority | Status | Next Action |
|-------|----------|--------|------------|
| Phase 2: YouTube Integration | 🔥 **HIGH** | ⏳ | Implement ytmusicapi/yt-dlp |
| Phase 3: Core Playback | High | ⏳ | Implement chunk caching |
| Phase 4: Frontend Buffering | High | ⏳ | Implement Web Audio API |
| Phase 5: Real-Time Fetching | Medium | ⏳ | Add buffer-ahead logic |
| Phase 6: Playback Frontend | Medium | ⏳ | Build React UI |
| Phase 7: Library Frontend | Medium | ⏳ | Build search/browse UI |
| Phase 8: Tauri Desktop | Medium | ⏳ | Package as desktop app |
| Phase 9: Android | Low | ⏳ | Add mobile support |
| Phase 10: Polish | Low | ⏳ | Error handling, optimization |

---

## 🎯 Next Steps (Phase 2: YouTube Integration)

### 📌 Current Step: Phase 2 - YouTube Integration

**Objective**: Replace mock data with real YouTube Music API calls.

### 📋 Task List for Phase 2

#### Task 1: Set Up YouTube API Services
- **File to Create**: `backend/services/youtube.py`
- **Status**: ⏳ TODO
- **Description**: Create service layer for YouTube Music API integration
- **Dependencies**: ytmusicapi (already installed)
- **Actions**:
  - [ ] Create `YouTubeService` class
  - [ ] Initialize ytmusicapi with OAuth/cookies
  - [ ] Add search method (songs, artists, albums, playlists)
  - [ ] Add get_song_metadata method
  - [ ] Add get_artist_info method
  - [ ] Add get_album_info method
  - [ ] Add get_playlist_info method

#### Task 2: Implement YouTube Authentication
- **File to Create**: `backend/services/auth.py`
- **File to Update**: `backend/config.py`
- **Status**: ⏳ TODO
- **Description**: Implement YouTube OAuth flow
- **Actions**:
  - [ ] Create OAuth flow handler
  - [ ] Add YouTube API credentials to config
  - [ ] Implement token storage (SQLite or encrypted file)
  - [ ] Add token refresh logic
  - [ ] Create auth endpoints:
    - `POST /api/auth/login` - Initiate OAuth
    - `POST /api/auth/callback` - Handle callback
    - `GET /api/auth/status` - Check auth status

#### Task 3: Update Endpoints with Real Data
- **File to Update**: `backend/api/endpoints.py`
- **Status**: ⏳ TODO
- **Description**: Replace mock data with real API calls
- **Actions**:
  - [ ] Update `/api/search` to use YouTubeService
  - [ ] Update `/api/song/{id}` to fetch real metadata
  - [ ] Update `/api/artist/{id}` to fetch real data
  - [ ] Update `/api/album/{id}` to fetch real data
  - [ ] Update `/api/playlist/{id}` to fetch real data
  - [ ] Add error handling for API failures

#### Task 4: Add Audio Streaming with yt-dlp
- **File to Create**: `backend/services/streaming.py`
- **Status**: ⏳ TODO
- **Description**: Implement audio streaming from YouTube
- **Dependencies**: yt-dlp (already installed)
- **Actions**:
  - [ ] Create `StreamingService` class
  - [ ] Implement chunk downloading from YouTube
  - [ ] Add format/quality selection (MP3, 192kbps)
  - [ ] Store chunks in `.amp/cache/chunks/`
  - [ ] Track metadata in `cached_chunks` table
  - [ ] Update `/api/stream/{song_id}` endpoint

#### Task 5: Add User Data Access
- **File to Update**: `backend/api/endpoints.py`
- **Status**: ⏳ TODO
- **Description**: Implement user-specific endpoints
- **Actions**:
  - [ ] Add `GET /api/user/playlists` - Get user playlists
  - [ ] Add `POST /api/user/playlists/{id}/add` - Add to playlist
  - [ ] Add `POST /api/user/playlists/{id}/remove` - Remove from playlist
  - [ ] Add `POST /api/user/likes` - Like/unlike song
  - [ ] Add `GET /api/user/likes` - Get liked songs

### ✅ Task Completion Checklist for Phase 2

- [ ] `backend/services/youtube.py` created and working
- [ ] `backend/services/auth.py` created and working
- [ ] YouTube OAuth flow implemented
- [ ] Real search functionality working
- [ ] Real metadata fetching working
- [ ] Audio streaming with yt-dlp working
- [ ] User data endpoints working
- [ ] All existing tests still pass
- [ ] New tests added for YouTube integration
- [ ] AGENTS.md updated with Phase 2 completion

---

## 📁 Files to Create/Modify for Phase 2

### New Files
| File | Purpose | Priority |
|------|---------|----------|
| `backend/services/__init__.py` | Services package init | High |
| `backend/services/youtube.py` | YouTube Music API integration | 🔥 High |
| `backend/services/auth.py` | YouTube OAuth flow | 🔥 High |
| `backend/services/streaming.py` | Audio streaming with yt-dlp | High |
| `backend/tests/test_youtube.py` | Tests for YouTube integration | Medium |

### Modified Files
| File | Changes | Priority |
|------|---------|----------|
| `backend/config.py` | Add YouTube API credentials | High |
| `backend/api/endpoints.py` | Replace mock data with real API calls | 🔥 High |
| `backend/database/models.py` | Minor updates if needed | Low |
| `backend/.env.example` | Add OAuth config | Medium |
| `AGENTS.md` | Update after completion | 🔥 High |

---

## 🔧 Commands to Remember

### Development
```bash
# Activate virtual environment
activate.bat

# Install new dependencies
pip install package-name

# Update requirements
pip freeze > backend/requirements.txt

# Run server
python backend/main.py

# Run tests
pytest backend/tests/ -v

# Run specific test
pytest backend/tests/test_endpoints.py::TestSearchEndpoint -v
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
├── backend/
│   ├── api/              # REST API endpoints
│   │   └── endpoints.py  # Main endpoint file to update
│   ├── database/        # Database models and sessions
│   │   ├── models.py    # SQLAlchemy models
│   │   └── session.py   # Database sessions
│   ├── services/        # Service layer (CREATE FOR PHASE 2)
│   │   ├── __init__.py  # Package init
│   │   ├── youtube.py   # YouTube API (Phase 2)
│   │   ├── auth.py      # OAuth flow (Phase 2)
│   │   └── streaming.py # Audio streaming (Phase 2)
│   ├── config.py        # Configuration
│   ├── main.py          # Server entry point
│   └── tests/           # Test suite
└── venv/               # Virtual environment
```

### Key Configuration Values
From `backend/config.py`:
```python
CACHE_DIR = BASE_DIR / ".amp" / "cache"
CHUNKS_DIR = CACHE_DIR / "chunks"
USERDB_PATH = BASE_DIR / "userdb.sqlite"
PLAYDB_PATH = BASE_DIR / "playdb.sqlite"
CHUNK_SIZE_SEC = 10  # Chunk duration in seconds
CACHE_MAX_SIZE_MB = 500  # Max cache size in MB
```

### API Endpoint Structure
All endpoints are in `backend/api/endpoints.py` with prefix `/api`.
Current endpoints return mock data - they need real YouTube API calls.

### Database Access Pattern
```python
from backend.database.session import get_userdb_session, get_playdb_session

db = next(get_userdb_session())
# Use db.query(...)
db.close()  # Automatic with context manager
```

---

## 🎯 Current Focus: Phase 2 - YouTube Integration

**You are here**: Phase 2, Task 1 - Create `backend/services/youtube.py`

### Immediate Next Actions
1. Create `backend/services/__init__.py`
2. Create `backend/services/youtube.py` with YouTubeService class
3. Test the service independently
4. Update `backend/api/endpoints.py` to use the service
5. Run tests to ensure nothing broke

### After Phase 2
Move to Phase 3: Core Playback System (chunk caching, streaming endpoint)

---

## 📊 Progress Tracking

### Phase Completion
| Phase | Start Date | End Date | Status | Commits |
|-------|------------|----------|--------|---------|
| Phase 1 | 2026-10-12 | 2026-10-12 | ✅ Complete | 8 commits |
| Phase 2 | - | - | ⏳ | - |
| Phase 3 | - | - | ⏳ | - |
| ... | - | - | ⏳ | - |

### Current Session
- **Started**: 2026-10-12
- **Current Task**: Phase 2, Task 1 - YouTube API Service
- **Last Updated**: 2026-10-12 (by Mistral Vibe)

---

## 💡 Tips for Agents

### Understanding the Codebase
1. Start with `backend/config.py` - understand the configuration
2. Read `backend/database/models.py` - understand the data structures
3. Read `backend/api/endpoints.py` - understand the API surface
4. Check `backend/tests/` - understand expected behavior

### Common Pitfalls
1. **Database Sessions**: Always use the session context manager or close sessions manually
2. **Path Issues**: Use `from backend.config import BASE_DIR` for paths
3. **Circular Imports**: Python can have import order issues - check `__init__.py` files
4. **Async Code**: FastAPI supports async - use it for I/O-bound operations
5. **Windows Paths**: Use `Path` from pathlib, not string paths

### Debugging Tips
1. **Check logs**: `.amp/logs/app.log` for application logs
2. **Run in debug mode**: `python backend/main.py --debug`
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
A: Check the "Next Steps" section above. Currently: Phase 2, Task 1 (YouTube API Service)

**Q: Where are the API endpoints?**  
A: `backend/api/endpoints.py`

**Q: How do I test my changes?**  
A: `pytest backend/tests/ -v`

**Q: How do I run the server?**  
A: `python backend/main.py`

**Q: What files should I read first?**  
A: See the "Essential Reading" section above.

---

## ✅ After Completing Work

### Update Checklist
Before ending your session, ensure you've:

1. **Updated AGENTS.md**:
   - [ ] Marked completed tasks
   - [ ] Updated current phase/status
   - [ ] Set next steps
   - [ ] Added any important notes or gotchas

2. **Committed Changes**:
   - [ ] All modified files are staged (`git add`)
   - [ ] Commit message is clear and descriptive
   - [ ] AGENTS.md is included in the commit

3. **Tested**:
   - [ ] All existing tests pass (`pytest backend/tests/ -v`)
   - [ ] New functionality works as expected
   - [ ] No regressions introduced

4. **Documented**:
   - [ ] README files updated if needed
   - [ ] Code comments added for complex logic
   - [ ] Configuration documented

### Example Workflow
```bash
# 1. Read instructions
# (Read AGENTS.md, ROADMAP.md, etc.)

# 2. Implement feature
# (Create/modify files)

# 3. Test
pytest backend/tests/ -v

# 4. Update AGENTS.md
# (Mark tasks complete, set next steps)

# 5. Commit
git add .
git commit -m "feat: implement YouTube API service"
git push origin master
```

---

## 🏁 Final Notes

This project is **well-structured** and **ready for continuation**. The foundation (Phase 1) is solid, and each subsequent phase builds logically on the previous one.

**Current Priority**: Phase 2 (YouTube Integration) is the next critical step. Without it, the app cannot access real YouTube data.

**Your Mission**: Implement Phase 2, update this file, and commit your changes. The next agent (or you in a future session) will pick up from where you left off.

---

**Last Updated**: 2026-10-12  
**Current Phase**: Phase 1 Complete, Phase 2 Next  
**Next Task**: Phase 2, Task 1 - Create `backend/services/youtube.py`  
**Status**: Ready for implementation 🚀
