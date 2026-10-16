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
**Current Phase**: Phase 2 (YouTube Integration) - ✅ COMPLETE  
**Next Phase**: Phase 3 (Core Playback) - ⏳ PENDING  

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

### ✅ Completed (Phase 2: YouTube Integration)

| Category | Status | Files | Notes |
|----------|--------|-------|-------|
| YouTube Service | ✅ Done | `backend/services/youtube.py` | YouTubeService class with search, metadata methods |
| Auth Service | ✅ Done | `backend/services/auth.py` | OAuth flow, token management, cookie handling |
| Streaming Service | ✅ Done | `backend/services/streaming.py` | Chunk downloading, caching, yt-dlp integration |
| Services Package | ✅ Done | `backend/services/__init__.py` | Package initialization |
| YouTube Tests | ✅ Done | `backend/tests/test_youtube.py` | 28 tests for YouTubeService |
| Auth Tests | ✅ Done | `backend/tests/test_auth.py` | 31 tests for AuthService |
| Streaming Tests | ✅ Done | `backend/tests/test_streaming.py` | 25 tests for StreamingService |
| Config Updates | ✅ Done | `backend/config.py` | Added YouTube OAuth credentials |
| Endpoints Updates | ✅ Done | `backend/api/endpoints.py` | Integrated services with mock fallback |
| Environment Template | ✅ Done | `backend/.env.example` | OAuth configuration template |

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
- **File to Update**: `backend/services/streaming.py`
- **Status**: ⏳ TODO
- **Description**: Enhance streaming service with robust chunk caching
- **Actions**:
  - [ ] Implement chunk cache eviction (LRU or size-based)
  - [ ] Add cache size monitoring and cleanup
  - [ ] Implement parallel chunk downloading
  - [ ] Add chunk pre-fetching for smooth playback
  - [ ] Handle cache corruption and recovery

#### Task 2: Implement Streaming Endpoints
- **File to Update**: `backend/api/endpoints.py`
- **Status**: ⏳ TODO
- **Description**: Add real streaming endpoints
- **Actions**:
  - [ ] Implement `GET /api/stream/{song_id}` endpoint
  - [ ] Add chunk range support for partial streaming
  - [ ] Implement streaming session management
  - [ ] Add bandwidth throttling and quality adaptation

#### Task 3: Add Playback State Management
- **File to Update**: `backend/services/streaming.py`
- **Status**: ⏳ TODO
- **Description**: Manage playback state across sessions
- **Actions**:
  - [ ] Implement playback position tracking
  - [ ] Add playback history logging
  - [ ] Implement resume from last position
  - [ ] Add crossfade support

#### Task 4: Add Buffer-Ahead Logic
- **File to Update**: `backend/services/streaming.py`
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
| `backend/services/__init__.py` | Services package init | High | ✅ Done |
| `backend/services/youtube.py` | YouTube Music API integration | 🔥 High | ✅ Done |
| `backend/services/auth.py` | YouTube OAuth flow | 🔥 High | ✅ Done |
| `backend/services/streaming.py` | Audio streaming with yt-dlp | High | ✅ Done |
| `backend/tests/test_youtube.py` | Tests for YouTube integration | Medium | ✅ Done |
| `backend/tests/test_auth.py` | Tests for Auth service | Medium | ✅ Done |
| `backend/tests/test_streaming.py` | Tests for Streaming service | Medium | ✅ Done |

### Modified Files
| File | Changes | Priority | Status |
|------|---------|----------|--------|
| `backend/config.py` | Add YouTube API credentials | High | ✅ Done |
| `backend/api/endpoints.py` | Replace mock data with real API calls | 🔥 High | ✅ Done |
| `backend/database/models.py` | Minor updates if needed | Low | ⏳ Pending |
| `backend/.env.example` | Add OAuth config | Medium | ✅ Done |
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
Endpoints now use real YouTube API calls via services, with mock data fallback for testing.

### Database Access Pattern
```python
from backend.database.session import get_userdb_session, get_playdb_session

db = next(get_userdb_session())
# Use db.query(...)
db.close()  # Automatic with context manager
```

---

## 🎯 Current Focus: Phase 3 - Core Playback System

**You are here**: Phase 3, Task 1 - Implement Chunk Caching System

### Immediate Next Actions
1. Enhance `backend/services/streaming.py` with chunk cache eviction
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
| Phase 3 | - | - | ⏳ | - | Core Playback |
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
1. Start with `backend/config.py` - understand the configuration
2. Read `backend/database/models.py` - understand the data structures
3. Read `backend/api/endpoints.py` - understand the API surface
4. Check `backend/tests/` - understand expected behavior
5. Review `backend/services/` - understand service layer patterns

### Common Pitfalls
1. **Database Sessions**: Always use the session context manager or close sessions manually
2. **Path Issues**: Use `from backend.config import BASE_DIR` for paths
3. **Circular Imports**: Python can have import order issues - check `__init__.py` files
4. **Async Code**: FastAPI supports async - use it for I/O-bound operations
5. **Windows Paths**: Use `Path` from pathlib, not string paths
6. **Singleton State**: When writing tests for singleton services, clean up global state between tests

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
A: Check the "Next Steps" section above. Currently: Phase 3, Task 1 (Chunk Caching System)

**Q: Where are the API endpoints?**  
A: `backend/api/endpoints.py`

**Q: How do I test my changes?**  
A: `pytest backend/tests/ -v`

**Q: How do I run the server?**  
A: `python backend/main.py`

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
   - [x] All existing tests pass (`pytest backend/tests/ -v`)
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

This project is **well-structured** and **ready for continuation**. The foundation (Phase 1) is solid, and Phase 2 (YouTube Integration) is now complete with all services implemented and tested.

**Current Priority**: Phase 3 (Core Playback System) is the next critical step. Without it, the app cannot provide smooth audio streaming.

**Your Mission**: Implement Phase 3, update this file, and commit your changes. The next agent (or you in a future session) will pick up from where you left off.

---

**Last Updated**: 2026-10-16  
**Current Phase**: Phase 2 Complete, Phase 3 Next  
**Next Task**: Phase 3, Task 1 - Implement Chunk Caching System  
**Status**: Ready for implementation 🚀
