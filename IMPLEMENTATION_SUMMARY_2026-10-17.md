# Implementation Summary - 2026-10-17

## Overview

This document summarizes two major changes made on 2026-10-17:

1. **Phase 2.5 - Authentication Overhaul**: Replaced the broken OAuth flow with a working cookie-based authentication system.
2. **Phase 2.6 - Web Interface Foundation**: Created a React web interface for testing without the Tauri desktop app.

---

## Phase 2.5: Authentication Overhaul

### Problem

The original OAuth-based auth was completely broken:

1. **OAuth is a dead end**: YouTube Music's private endpoints stopped accepting OAuth tokens around September 2025.
2. **ytmusicapi API mismatches**: `YTMusic(headers_raw=...)`, `YTMusic(token=...)`, and `YTMusic(cookies_file=...)` don't exist in ytmusicapi 1.12.3.
3. **Two separate auth states**: `AuthService` and `YouTubeService` each tracked their own state, so `YouTubeService` never learned about a login.
4. **Manual cookie extraction was broken**: Chrome encrypts cookie values; the script read empty strings.
5. **Code bugs**: `"is_automated": true` (Python `NameError`), triplicated `REDIRECT_URI` blocks, etc.

### Solution: Cookie-Based Auth

The new system uses **browser session cookies** — the only method YouTube Music accepts.

**Auth flow**:
1. User clicks "Connect YouTube Music"
2. Tauri opens a Google sign-in window (`youtube_login.rs`)
3. User logs in (including 2FA)
4. Tauri reads session cookies from the webview (requires Tauri 2.4+)
5. Frontend POSTs cookies to `POST /api/auth/cookies`
6. Backend validates against YouTube, saves to `.amp/cache/ytm_session.json` (0600)
7. All services use `get_auth_service().client` — single source of truth

**Fallback**: `POST /api/auth/import-browser` uses yt-dlp to import cookies from Firefox (Chrome on Windows often blocked).

### Files Changed

| File | Change |
|------|--------|
| `amp/backend/services/auth.py` | **Completely replaced** — new cookie-based AuthService |
| `amp/backend/api/auth_routes.py` | **New** — `/auth/status`, `/auth/cookies`, `/auth/import-browser`, `/auth/logout` |
| `amp/backend/services/youtube.py` | Updated to use centralized auth service |
| `amp/backend/api/endpoints.py` | Removed old OAuth endpoints, added auth_router |
| `amp/backend/config.py` | Removed OAuth credentials (YOUTUBE_CLIENT_ID, etc.) |
| `app/src-tauri/src/youtube_login.rs` | **New** — Tauri command for Google sign-in window |
| `app/src-tauri/main.rs` | Updated to use youtube_login command |
| `app/src-tauri/Cargo.toml` | Added tokio with time feature |
| `amp/backend/tests/test_ytm_auth.py` | **New** — 11 tests for auth service |
| `amp/backend/tests/test_auth.py` | **Deleted** — old OAuth tests |
| `app/scripts/extract_cookies.py` | **Deleted** — didn't work (Chrome encrypts cookies) |

---

## Phase 2.6: Web Interface Foundation

### Problem

The Tauri desktop app couldn't be built on Windows (missing Visual Studio Build Tools with C++ workload). The user needed a way to test the app.

### Solution: Web Interface

Created a standalone React web interface that works without Tauri:

- **Vite dev server** on port 1420 (`npm run dev`)
- **`useYouTubeAuth` React hook** for auth state management
- **Auth UI**: "Connect YouTube Music" button, status display, liked songs
- **Fixed Tauri 2.x project structure** (moved Cargo.toml and tauri.conf.json to `src-tauri/`)

### Files Changed

| File | Change |
|------|--------|
| `app/src/useYouTubeAuth.ts` | **New** — React hook for auth state |
| `app/src/App.tsx` | Simplified to use `useYouTubeAuth` hook |
| `app/src-tauri/Cargo.toml` | **Moved** from `app/`, fixed dependencies |
| `app/src-tauri/tauri.conf.json` | **Moved** from `app/`, updated to Tauri 2.x |
| `app/src-tauri/build.rs` | **New** — Tauri build script |
| `app/src-tauri/src/main.rs` | **Moved** from `app/src-tauri/main.rs` |
| `app/package.json` | Updated scripts (dev, tauri:dev, tauri:build) |

---

## Testing

All **92 tests** pass:

```bash
cd amp/backend
python -m pytest tests/ -v
```

Test breakdown:
- Phase 1 (Backend Core): 20 tests
- Phase 2 (YouTube): 28 tests
- Phase 2 (Streaming): 25 tests
- Phase 2.5 (Auth): 11 tests (new)
- Other: 8 tests

---

## How to Test

### Backend only:
```bash
python amp/backend/main.py
# → http://localhost:8000
```

### Web interface:
```bash
# Terminal 1: Backend
python amp/backend/main.py

# Terminal 2: Frontend
cd app
npm run dev
# → http://localhost:1420
```

### Auth via browser import:
```bash
curl -X POST http://localhost:8000/api/auth/import-browser \
  -H "Content-Type: application/json" \
  -d '{"browser": "firefox"}'
```

---

## What's Next

**Phase 3: Core Playback System** — Implement chunk-based audio streaming and caching.

See [ROADMAP.md](ROADMAP.md) for details.
