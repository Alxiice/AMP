# AMP - Implementation Notes

> **Current Phase**: Phase 2 (YouTube Integration) — ✅ COMPLETE
> **Next Phase**: Phase 3 (Core Playback System) — ⏳ READY TO START
> **Tests**: 92/92 passing

---

## Phase 1: Backend Core (2026-10-12) ✅

### What was built

FastAPI backend skeleton with SQLAlchemy, SQLite, and a full test suite.

| Component | Details |
|-----------|---------|
| Server | FastAPI + Uvicorn, CORS enabled |
| Database | SQLAlchemy ORM, 10 tables (userdb + playdb) |
| Config | Pydantic Settings, `.env` support |
| Logging | File + console output |
| Endpoints | 12 REST endpoints (health, search, library, queue, playback) |
| Tests | 20 tests (setup, models, endpoints) |
| Venv | Pre-configured Python virtual environment |

### Key decisions

- **FastAPI over Flask**: Async-native, auto OpenAPI docs
- **Tauri over Electron**: ~5MB vs ~100MB bundle size
- **Frontend playback**: Web Audio API handles buffering/EQ, not the backend
- **Filesystem for chunks**: 10-100x faster than SQLite BLOBs

---

## Phase 2: YouTube Integration (2026-10-16 to 2026-10-17) ✅

### What was built

Full YouTube Music integration with metadata, streaming, authentication, and a web interface.

### 2a. YouTube Music API (2026-10-16)

| Component | Details |
|-----------|---------|
| `services/youtube.py` | `YouTubeService` — search, song/artist/album/playlist metadata via ytmusicapi |
| `services/streaming.py` | `StreamingService` — chunk downloading, caching, yt-dlp integration |
| Tests | 28 YouTube tests + 25 streaming tests |
| Endpoints | All endpoints wired to real services |

### 2b. Authentication Overhaul (2026-10-17)

**Problem**: The original OAuth flow was completely broken.

- YouTube Music's private endpoints stopped accepting OAuth tokens (~Sept 2025)
- `ytmusicapi` API mismatches: `YTMusic(headers_raw=...)`, `YTMusic(token=...)` don't exist
- Two separate auth states (`AuthService` + `YouTubeService`) caused split-brain
- `extract_cookies.py` couldn't work (Chrome encrypts cookies)
- Code bugs: `"is_automated": true` (NameError), triplicated REDIRECT_URI blocks

**Solution**: Cookie-based authentication — the only method YouTube Music accepts.

| Component | Details |
|-----------|---------|
| `services/auth.py` | Rewritten: single-source-of-truth `AuthService` with cookie validation, session persistence (0600), expiry detection |
| `api/auth_routes.py` | New: `GET /auth/status`, `POST /auth/cookies`, `POST /auth/import-browser`, `POST /auth/logout` |
| `services/youtube.py` | Updated to use `get_auth_service().client` |
| `config.py` | Removed OAuth credentials |
| `app/src-tauri/src/youtube_login.rs` | New: Tauri command — opens Google sign-in window, captures cookies |
| `app/src/useYouTubeAuth.ts` | New: React hook for auth state management |
| Tests | +11 new auth tests (`test_ytm_auth.py`), deleted old `test_auth.py` |

**Auth flow**:
1. User clicks "Connect YouTube Music"
2. Tauri opens Google sign-in window → user logs in (incl. 2FA)
3. Tauri captures session cookies → frontend POSTs to `/api/auth/cookies`
4. Backend validates against YouTube, saves to `.amp/cache/ytm_session.json` (0600)
5. All services use `get_auth_service().client` — single source of truth

**Fallback**: `POST /api/auth/import-browser` with `{"browser": "firefox"}` (yt-dlp cookie extraction)

### 2c. Web Interface Foundation (2026-10-17)

**Problem**: Tauri desktop build blocked on Windows (missing Visual Studio Build Tools with C++ workload). No way to test the UI.

**Solution**: Standalone React web interface via Vite dev server.

| Component | Details |
|-----------|---------|
| `app/src/App.tsx` | Auth UI: "Connect" button, status display, liked songs |
| `app/src/useYouTubeAuth.ts` | React hook: `status`, `login()`, `logout()`, `importFromBrowser()` |
| `app/vite.config.ts` | Dev server on port 1420, proxies `/api/*` to backend |
| Tauri structure | Fixed: `Cargo.toml` and `tauri.conf.json` moved to `src-tauri/`, created `build.rs` |

**Test**: `cd app && npm run dev` → http://localhost:1420

---

## Test Summary

| Phase | Tests | Files |
|-------|-------|-------|
| Phase 1 | 20 | `test_setup.py` (3), `test_models.py` (4), `test_endpoints.py` (13) |
| Phase 2a | 53 | `test_youtube.py` (28), `test_streaming.py` (25) |
| Phase 2b | 11 | `test_ytm_auth.py` (11) |
| Phase 2c | 8 | Additional endpoint/auth tests |
| **Total** | **92** | |

---

## File Inventory (Phase 2)

### Backend
```
amp/backend/
├── services/
│   ├── youtube.py          # YouTube Music API (ytmusicapi)
│   ├── auth.py             # Cookie-based auth (single source of truth)
│   └── streaming.py        # Audio streaming (yt-dlp)
├── api/
│   ├── endpoints.py        # Main API routes
│   └── auth_routes.py      # Auth routes
└── tests/
    ├── test_youtube.py     # 28 tests
    ├── test_streaming.py   # 25 tests
    └── test_ytm_auth.py    # 11 tests
```

### Frontend
```
app/
├── src/
│   ├── App.tsx             # Main app (auth UI, liked songs)
│   ├── useYouTubeAuth.ts   # Auth React hook
│   └── index.css           # Styles
└── src-tauri/              # Tauri desktop (structure ready, needs Rust build tools)
    ├── src/
    │   ├── main.rs
    │   └── youtube_login.rs  # Google sign-in window
    ├── Cargo.toml
    └── tauri.conf.json
```

---

## What's Next: Phase 3 — Core Playback System

- Chunk cache manager (filesystem-based in `.amp/cache/chunks/`)
- `GET /api/stream/{song_id}` streaming endpoint
- Playback state management (position tracking, resume)
- Buffer-ahead logic for smooth playback

See [ROADMAP.md](ROADMAP.md) for the full plan.
