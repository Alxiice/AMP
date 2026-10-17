# YouTube Authentication Flow Guide

## Overview

This document explains the YouTube authentication flow implemented in AMP and how to test it.

## Authentication Methods

AMP supports **two authentication modes**:

### Mode 1: OAuth with Credentials (Recommended for App Developer)
- Requires: Google OAuth Client ID and Client Secret (created by **you**, the app developer)
- Opens browser automatically for OAuth flow
- Best user experience
- Tokens are saved and refreshed automatically

### Mode 2: Cookie-Based Auth (No Credentials)
- No Google OAuth credentials required
- Opens YouTube Music in browser
- User must manually copy request headers from browser
- Headers are saved and reused

## Current Implementation

The `trigger_cookie_auth()` endpoint automatically uses:
- **Mode 1** if `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET` are configured
- **Mode 2** if credentials are not configured

## Configuration

### Option A: Use OAuth Credentials (Recommended)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable "YouTube Data API v3"
4. Create OAuth 2.0 credentials (Client ID and Client Secret)
5. Add authorized redirect URI: `http://localhost:8000/api/auth/callback`
6. Add the credentials to your `.env` file:

```bash
YOUTUBE_CLIENT_ID=your_client_id.apps.googleusercontent.com
YOUTUBE_CLIENT_SECRET=your_client_secret
```

**Benefits**: 
- Users don't need to create credentials
- Browser opens automatically
- Seamless OAuth flow

### Option B: Use Cookie-Based Auth (No Credentials)

No configuration needed. The app will:
1. Open YouTube Music in your browser
2. Ask you to log in
3. Prompt you to copy request headers from the browser

**Trade-offs**:
- Manual step required (copy headers)
- Less seamless user experience
- Still works without any credentials

## Testing the Auth Flow

### Step 1: Start the Backend

```bash
python amp/backend/main.py
```

### Step 2: Trigger Authentication

Send a POST request to trigger cookie auth:

```bash
curl -X POST http://localhost:8000/api/auth/cookie-auth
```

Or use the frontend:
- Open `http://localhost:3000` (if using dev server)
- Click "Login with YouTube Music" button

### Step 3: Complete Authentication

#### If using OAuth (credentials configured):
1. A browser window will open to Google's OAuth page
2. Log in to your Google account
3. Grant permissions
4. You'll be redirected back
5. Tokens are saved automatically

#### If using Cookie-Based Auth (no credentials):
1. A browser window will open to YouTube Music
2. Log in to your YouTube account
3. In the browser:
   - Open Developer Tools (F12 or Ctrl+Shift+I)
   - Go to Network tab
   - Refresh the page (F5)
   - Find a request to `/browse`
   - Right-click → Copy → Copy as cURL
4. In the terminal where you ran the backend:
   - Paste the copied cURL command
   - Press Enter, then Ctrl+Z (Windows) or Ctrl+D (Mac/Linux)
5. Headers are saved automatically

### Step 4: Verify Authentication

Check auth status:

```bash
curl http://localhost:8000/api/auth/status
```

Expected response:
```json
{
  "is_authenticated": true,
  "has_tokens": true,
  "user_info": { ... },
  "client_configured": false
}
```

### Step 5: Retrieve Liked Songs

```bash
curl http://localhost:8000/api/user/likes
```

This will return your liked songs from YouTube Music.

## Files Modified

### Backend (`amp/backend/services/auth.py`)
- `trigger_cookie_auth()`: Handles both OAuth and cookie-based auth
- `_authenticate_with_ytmusic_token()`: Authenticates with OAuth token
- `_authenticate_with_headers()`: Authenticates with browser headers

### API (`amp/backend/api/endpoints.py`)
- `/api/auth/cookie-auth`: Endpoint to trigger authentication
- Removed duplicate endpoint definitions

## Frontend Integration

The frontend (`app/src/App.tsx`) automatically:
1. Calls `/api/auth/cookie-auth` when user clicks login
2. Shows auth progress message
3. Polls for authentication status every 2 seconds
4. Updates UI when authenticated
5. Displays liked songs after authentication

## Tauri App

The Tauri desktop app (`app/`) includes:
- Proper configuration (`tauri.conf.json`)
- Shell plugin for opening browser
- HTTP plugin for API requests
- Frontend that works with Tauri

To run:
```bash
cd app
npm run tauri:dev
```

## Troubleshooting

### Issue: Browser doesn't open
**Solution**: Check if `webbrowser` module can open your default browser. Try:
```python
import webbrowser
webbrowser.open("https://music.youtube.com")
```

### Issue: OAuth fails with "client_id not configured"
**Solution**: Add `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET` to your `.env` file

### Issue: Headers not accepted
**Solution**: Make sure you're copying from a request to `/browse` (not other endpoints). The headers must include `cookie` and `x-goog-authuser`.

### Issue: Authentication succeeds but can't get liked songs
**Solution**: Check if you're authenticated first:
```bash
curl http://localhost:8000/api/auth/status
```
If `is_authenticated` is false, try authenticating again.

## Environment Variables

Create a `.env` file in `amp/backend/`:

```bash
# For OAuth flow (recommended)
YOUTUBE_CLIENT_ID=your_client_id.apps.googleusercontent.com
YOUTUBE_CLIENT_SECRET=your_client_secret
YOUTUBE_REDIRECT_URI=http://localhost:8000/api/auth/callback

# Optional: YouTube API key (for additional features)
YOUTUBE_API_KEY=your_api_key

# Optional: Path to cookies file
YTMUSICAPI_COOKIES=.amp/cache/cookies.json
```

## Security Notes

1. **Never commit credentials to version control**
   - Add `.env` to `.gitignore`
   - Don't commit credentials in source code

2. **OAuth tokens are saved locally**
   - Tokens are saved to `.amp/cache/` directory
   - They're only accessible on the local machine

3. **Headers contain cookies**
   - Headers copied from browser contain session cookies
   - They allow access to your YouTube account
   - Keep them secure

## Re-authentication

To re-authenticate (e.g., with a different account):

```bash
# Logout first
curl -X POST http://localhost:8000/api/auth/logout

# Then authenticate again
curl -X POST http://localhost:8000/api/auth/cookie-auth
```

## Summary

| Method | Credentials | User Experience | Automatic? |
|--------|-------------|----------------|------------|
| OAuth | Required (developer) | ⭐⭐⭐⭐⭐ | ✅ Yes |
| Cookie-based | Not required | ⭐⭐ | ❌ No (manual copy) |

**Recommendation**: Use OAuth with your own credentials for the best user experience.
