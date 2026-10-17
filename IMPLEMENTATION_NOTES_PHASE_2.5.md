# AMP - Phase 2.5 Implementation Notes: Authentication Overhaul

> **Phase**: 2.5 (Authentication Overhaul)
> **Status**: ✅ COMPLETE
> **Date**: 2026-10-17
> **Branch**: `fix/auth`

---

## 📌 Executive Summary

Phase 2.5 replaced the completely broken OAuth-based authentication with a working **cookie-based authentication system**. YouTube Music's private endpoints stopped accepting OAuth tokens around September 2025, making the old approach a dead end. The new system uses browser session cookies — the only method that still works.

**Result**: A fully functional auth system with 11 new tests, session persistence, and expiration detection. All 92 tests pass.

---

## 🎯 Problem Statement

The original auth system had **five independent failure points**:

### 1. OAuth is a dead end for YouTube Music

YouTube Music has no public API. `ytmusicapi` uses private endpoints (`music.youtube.com/youtubei/v1/...`). According to ytmusicapi users and the multi-scrobbler project, **OAuth clients stopped being accepted by those endpoints around September 2025**. The "authorize on a Google page" flow doesn't exist for YouTube Music anymore.

The custom PKCE flow was also dead code:
- Requested `youtube.readonly` tokens that ytmusicapi can't use
- Google redirects with a GET to a route defined as POST

### 2. ytmusicapi API mismatches

Checked against installed ytmusicapi 1.12.3:

| Broken call | Reality |
|-------------|---------|
| `YTMusic(headers_raw=...)` | Doesn't exist |
| `YTMusic(token=...)` | Doesn't exist |
| `YTMusic(cookies_file=...)` | Doesn't exist |
| `get_user()` | Requires `channelId` parameter |
| `get_user_playlists()` | Requires `channelId` parameter |
| `get_liked_songs()` | Returns a dict, not a list |
| `"is_automated": true` | `NameError` — Python literal is `True` |

### 3. Two separate auth states

`AuthService` and `YouTubeService` each tracked their own auth state. `YouTubeService` never learned about a login. `/user/likes` passed the first check and then returned `[]` from the second.

### 4. Manual cookie extraction was broken

- `ytmusicapi.setup()` reads stdin from a daemon thread inside uvicorn — doesn't work
- `extract_cookies.py` couldn't work: Chrome encrypts cookie values (reads empty strings)
- Lowercased cookie names (they're case-sensitive)
- Printed secrets to stdout

### 5. Code clutter

- Triplicated `REDIRECT_URI` blocks in `auth.py`
- Guide that contradicted itself about needing credentials

---

## 🏗️ Solution Architecture

### New Auth Flow

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Frontend   │────▶│  AuthService      │────▶│  ytmusicapi      │
│  (React)     │     │  (single source   │────▶│  YTMusic(client) │
│              │◀────│   of truth)       │◀────│                  │
└─────────────┘     └──────────────────┘     └─────────────────┘
                            │
                            ▼
                    ┌──────────────────┐
                    │  ytm_session.json │  (.amp/cache/, 0600)
                    │  (persisted)      │
                    └──────────────────┘
```

### Auth Methods

| Method | Endpoint / Command | Use Case |
|--------|-------------------|----------|
| Browser import | `POST /api/auth/import-browser` | Development, quick testing (Firefox recommended) |
| Tauri sign-in | `invoke("youtube_login")` → `POST /api/auth/cookies` | Production desktop app |

### Auth States

| State | Meaning |
|-------|---------|
| `signed_out` | No session, user needs to connect |
| `signed_in` | Valid session, API calls work |
| `expired` | Session was valid but YouTube rejected it |

---

## 📊 Files Changed

### New Files
| File | Purpose |
|------|---------|
| `amp/backend/api/auth_routes.py` | Auth API routes (status, cookies, import-browser, logout) |
| `amp/backend/tests/test_ytm_auth.py` | 11 tests for the new auth service |
| `app/src-tauri/src/youtube_login.rs` | Tauri command: opens Google sign-in window, captures cookies |

### Modified Files
| File | Changes |
|------|---------|
| `amp/backend/services/auth.py` | **Completely replaced** — cookie-based AuthService |
| `amp/backend/services/youtube.py` | Removed own auth state, uses `get_auth_service().client` |
| `amp/backend/api/endpoints.py` | Removed old OAuth endpoints, added `auth_router` |
| `amp/backend/config.py` | Removed OAuth credentials |
| `app/src-tauri/main.rs` | Added `youtube_login` module and command |
| `app/src-tauri/Cargo.toml` | Added `tokio` with `time` feature |

### Deleted Files
| File | Reason |
|------|--------|
| `amp/backend/tests/test_auth.py` | Old OAuth tests, replaced by `test_ytm_auth.py` |
| `app/scripts/extract_cookies.py` | Didn't work (Chrome encrypts cookies) |

---

## 🔑 Key Design Decisions

### 1. Single Source of Truth

`AuthService` is the **only** owner of auth state. `YouTubeService` and `StreamingService` get the authenticated client via `get_auth_service().client`. No more split-brain auth.

### 2. Session Persistence Without Network

On app launch, the session is restored from `.amp/cache/ytm_session.json` **without making a network call**. The ytmusicapi constructor makes a network call, so an offline start must not look like a logout.

### 3. Secure Storage

Session file has **0600 permissions** (owner read/write only). On Windows, ACLs are used.

### 4. Expiration Detection

A `guard()` context manager wraps API calls. If YouTube rejects the session, the state flips to `expired`, and the UI prompts for re-login.

### 5. Cookie Normalization

Cookies from different sources (Tauri webview, yt-dlp) are normalized to a consistent format before validation.

---

## 🧪 Testing

11 new tests in `test_ytm_auth.py`:

| Test | What it verifies |
|------|-----------------|
| `test_cookie_normalization` | Cookies from different formats are normalized correctly |
| `test_header_building` | Cookie header is built correctly for ytmusicapi |
| `test_initial_state` | AuthService starts as `signed_out` |
| `test_sign_in_with_cookies` | Sign-in flow works with valid cookies |
| `test_sign_in_invalid_cookies` | Invalid cookies are rejected |
| `test_sign_out` | Sign-out clears state and session file |
| `test_session_persistence` | Session is saved and restored from disk |
| `test_session_expiry` | Expired sessions are detected |
| `test_guard_signed_in` | `guard()` allows API calls when signed in |
| `test_guard_signed_out` | `guard()` raises when signed out |
| `test_guard_expired` | `guard()` raises when expired |

All tests use mock cookies — no real YouTube validation during tests.

---

## ⚠️ Caveats

1. **Embedded-webview sign-in is the riskiest part**: Google sometimes shows "This browser or app may not be secure" in embedded webviews. The browser-import shortcut is the fallback.
2. **Unofficial and grey area**: This uses YouTube Music's private endpoints via browser session cookies. It can break when Google changes things.
3. **Cookies = full account access**: The saved cookies provide full access to the Google account. Treat them as secrets.
4. **Platform support**: The Tauri sign-in window needs testing on Windows (WebView2), macOS (WKWebView), and Linux (WebKitGTK).

---

## 🚀 Next Steps

- Test the complete auth flow end-to-end
- Continue to **Phase 3: Core Playback System** (chunk caching, streaming endpoints)
