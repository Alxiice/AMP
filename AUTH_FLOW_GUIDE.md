# YouTube Authentication Flow Guide

## Overview

AMP uses **cookie-based authentication** with YouTube Music. This is the only method that works, because YouTube Music's private endpoints stopped accepting OAuth tokens in ~September 2025.

The auth system uses a **single source of truth** (`AuthService`) that all other services share.

---

## Auth States

| State | Meaning |
|-------|---------|
| `signed_out` | No session, user needs to connect |
| `signed_in` | Valid session, API calls work |
| `expired` | Session was valid but YouTube rejected it; user needs to re-login |

---

## Auth Methods

### Method 1: Browser Import (Recommended for development)

Uses yt-dlp to extract cookies from an installed browser.

```bash
curl -X POST http://localhost:8000/api/auth/import-browser \
  -H "Content-Type: application/json" \
  -d '{"browser": "firefox"}'
```

**Supported browsers**: `firefox`, `chrome`, `chromium`, `edge`, `brave`, `opera`, `vivaldi`, `safari`

**Notes**:
- Firefox works best. Chrome on Windows may be blocked by app-bound encryption.
- The browser must be closed while importing (yt-dlp reads the cookie database).

### Method 2: Tauri Sign-in Window (Recommended for production)

The Tauri desktop app opens a Google sign-in window. After the user logs in, Tauri reads the session cookies from the webview and sends them to the backend.

**Flow**:
1. Frontend calls `invoke("youtube_login")` (Tauri command)
2. Tauri opens a window to `https://accounts.google.com/v3/signin/...`
3. User signs in (including 2FA if enabled)
4. Tauri reads `__Secure-3PAPISID` and other session cookies from the webview
5. Frontend POSTs cookies to `POST /api/auth/cookies`
6. Backend validates cookies against YouTube Music

**Requirements**:
- Tauri 2.4+ (for webview cookie API)
- Rust build tools (Visual Studio Build Tools on Windows)

---

## API Endpoints

### `GET /api/auth/status`

Get current auth status. Add `?verify=true` to validate against YouTube.

```bash
curl http://localhost:8000/api/auth/status
```

Response:
```json
{
  "state": "signed_in",
  "account": {
    "name": "Your Name",
    "channelId": "UC..."
  }
}
```

### `POST /api/auth/cookies`

Receive cookies from the Tauri sign-in window.

```bash
curl -X POST http://localhost:8000/api/auth/cookies \
  -H "Content-Type: application/json" \
  -d '{
    "cookies": [
      {"name": "__Secure-3PAPISID", "value": "...", "domain": ".youtube.com", "path": "/"},
      {"name": "...", "value": "...", "domain": "...", "path": "/"}
    ]
  }'
```

### `POST /api/auth/import-browser`

Import cookies from an installed browser using yt-dlp.

```bash
curl -X POST http://localhost:8000/api/auth/import-browser \
  -H "Content-Type: application/json" \
  -d '{"browser": "firefox"}'
```

### `POST /api/auth/logout`

Clear the auth session.

```bash
curl -X POST http://localhost:8000/api/auth/logout
```

---

## Session Persistence

- Sessions are saved to `.amp/cache/ytm_session.json`
- File permissions: **0600** (owner read/write only)
- On app launch, the session is restored from disk **without a network call**
- If YouTube rejects the session later, the state flips to `expired`

---

## Frontend Integration

The React hook `useYouTubeAuth` (`app/src/useYouTubeAuth.ts`) manages auth state:

```typescript
import { useYouTubeAuth } from './useYouTubeAuth';

function App() {
  const { status, busy, error, login, logout, importFromBrowser } = useYouTubeAuth();

  // status: 'signed_out' | 'signed_in' | 'expired'
  // login() - opens Tauri sign-in window
  // importFromBrowser('firefox') - imports from browser
  // logout() - clears session
}
```

---

## Security Notes

1. **Cookies = Full Account Access**: The saved cookies provide full access to the Google account. Treat them as secrets.
2. **Never commit sessions**: `.amp/cache/ytm_session.json` is in `.gitignore`
3. **File permissions**: Session file is created with 0600 permissions
4. **Unofficial API**: This uses YouTube Music's private endpoints. It can break if Google changes things.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "This browser or app may not be secure" | Google blocks embedded webviews sometimes. Use browser import instead. |
| Chrome import returns empty | Chrome on Windows uses app-bound encryption. Use Firefox. |
| Session expired after a while | Cookies can be revoked. Re-login via browser import or sign-in window. |
| `state: "expired"` on launch | The session was valid but YouTube rejected it. Re-login. |
| Offline start shows `signed_out` | This should NOT happen. The session restores from disk without network. If it does, check file permissions on `ytm_session.json`. |

---

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Frontend   │────▶│  AuthService      │────▶│  ytmusicapi      │
│  (React)     │     │  (single source   │     │  (YTMusic client) │
│              │◀────│   of truth)       │◀────│                  │
└─────────────┘     └──────────────────┘     └─────────────────┘
                            │
                            ▼
                    ┌──────────────────┐
                    │  ytm_session.json │  (.amp/cache/, 0600)
                    │  (persisted)      │
                    └──────────────────┘
```

All services (`YouTubeService`, `StreamingService`) use `get_auth_service().client` to get the authenticated YTMusic instance. There is no separate auth state.
