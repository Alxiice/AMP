# DEPRECATED: Solution Summary - Old OAuth Approach

> **This document is outdated.** It describes the old OAuth-based authentication approach that was completely replaced on 2026-10-17.
>
> **For current documentation, see:**
> - [AUTH_FLOW_GUIDE.md](AUTH_FLOW_GUIDE.md) — Current cookie-based auth flow
> - [QUICK_START.md](QUICK_START.md) — How to get started
> - [IMPLEMENTATION_SUMMARY_2026-10-17.md](IMPLEMENTATION_SUMMARY_2026-10-17.md) — What changed

---

## Why This Was Replaced

The OAuth approach described below **does not work** for YouTube Music:

1. YouTube Music uses private endpoints, not the public YouTube Data API
2. Those private endpoints stopped accepting OAuth tokens in ~September 2025
3. The `ytmusicapi` library's OAuth support (`setup_oauth`) doesn't work with these endpoints anymore
4. Only **browser session cookies** are accepted

---

## Original Content (Deprecated)

<details>
<summary>Click to expand old OAuth documentation</summary>

## Your Goal

You want:
1. ✅ Auth with your YouTube account
2. ✅ Retrieve your liked videos
3. ❌ Fully automated auth WITHOUT Google OAuth credentials

## The Reality Check

**Item #3 is NOT possible.** YouTube's API requires authentication, and there are only TWO ways:

### Option A: OAuth 2.0 (Recommended) ✅
- **You** (developer) create Google OAuth credentials **once**
- Users click login → Browser opens → User logs in → Done
- Fully automated for users
- Industry standard (Spotify, etc. use this)

### Option B: Cookie-Based (Manual) ⚠️
- No credentials needed
- Browser opens to YouTube Music
- User must manually copy request headers from browser
- Not fully automated

**There is NO Option C for fully automated auth without credentials.**

### How to Get Fully Automated Auth

#### Step 1: Create Google OAuth Credentials (5 minutes)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create project "AMP Music Player"
3. Enable "YouTube Data API v3"
4. Create OAuth 2.0 Client ID:
   - Application type: **Web application**
   - Authorized JavaScript origins: `http://localhost:8000`
   - Authorized redirect URIs: `http://localhost:8000/api/auth/callback`
5. Copy **Client ID** and **Client Secret**

#### Step 2: Add to Backend

Create `.env` in `amp/backend/`:
```bash
YOUTUBE_CLIENT_ID=your_client_id.apps.googleusercontent.com
YOUTUBE_CLIENT_SECRET=your_client_secret
```

#### Step 3: Test

```bash
# Start backend
python amp/backend/main.py

# Get OAuth URL
curl -X POST http://localhost:8000/api/auth/login
```

Open the returned URL in browser → Log in → Done! ✅

</details>

---

## Current Auth System (2026-10-17)

The replacement system uses **cookie-based authentication**:

| Method | How | Best For |
|--------|-----|----------|
| Browser import | `POST /api/auth/import-browser` with `{"browser": "firefox"}` | Development, quick testing |
| Tauri sign-in | Click "Connect" in the app, sign in via popup window | Production desktop app |

No Google Cloud credentials are needed. See [AUTH_FLOW_GUIDE.md](AUTH_FLOW_GUIDE.md) for details.
