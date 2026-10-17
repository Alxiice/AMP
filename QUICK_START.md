# Quick Start Guide - YouTube Authentication

## The Issue You're Facing

You want **fully automated** YouTube authentication without users needing Google OAuth credentials.

## The Reality

**There is NO fully automated way to authenticate with YouTube Music without OAuth credentials.**

YouTube requires authentication, and the only automated methods are:
1. **OAuth 2.0** - Requires client_id and client_secret (YOU create these once)
2. **Cookies** - Requires manual header copying from browser

## Recommended Solution: OAuth with YOUR Credentials

As the **app developer**, YOU create the OAuth credentials once, and embed them in your app. Your **users** don't need to create anything.

### Step 1: Create Google OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (e.g., "AMP Music Player")
3. Enable the **YouTube Data API v3**:
   - Navigate to "APIs & Services" → "Library"
   - Search for "YouTube Data API v3"
   - Click "Enable"

4. Create OAuth 2.0 credentials:
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "OAuth client ID"
   - Select "Web application"
   - Name: "AMP Desktop Client"
   - Authorized JavaScript origins: `http://localhost:8000`
   - Authorized redirect URIs: `http://localhost:8000/api/auth/callback`
   - Click "Create"

5. Copy the **Client ID** and **Client Secret**

### Step 2: Add Credentials to Backend

Create or edit `.env` file in `amp/backend/`:

```bash
YOUTUBE_CLIENT_ID=your_client_id.apps.googleusercontent.com
YOUTUBE_CLIENT_SECRET=your_client_secret
YOUTUBE_REDIRECT_URI=http://localhost:8000/api/auth/callback
```

**DO NOT commit this file to version control!** Add `.env` to `.gitignore`.

### Step 3: Test the OAuth Flow

```bash
# Start backend
python amp/backend/main.py

# Get OAuth URL
curl -X POST http://localhost:8000/api/auth/login
```

You'll get a response like:
```json
{
  "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=...&redirect_uri=...&...",
  "message": "Redirect user to this URL to authenticate"
}
```

Open that URL in your browser, log in to Google, and you'll be redirected to `http://localhost:8000/api/auth/callback`. The backend will automatically exchange the code for tokens and save them.

### Step 4: Use the Frontend

```bash
# Terminal 1: Backend
python amp/backend/main.py

# Terminal 2: Build and serve frontend
cd app
npm run build
npm run serve
```

Open `http://localhost:3000` and click "Login with YouTube Music". The frontend will:
1. Call `/api/auth/login` to get OAuth URL
2. Open the URL in a new browser tab
3. After you log in, poll for authentication status
4. Show your liked songs once authenticated!

## Alternative: Cookie-Based Auth (No Credentials)

If you don't want to create OAuth credentials, use the cookie-based auth:

```bash
# Start backend
python amp/backend/main.py

# Trigger cookie auth
curl -X POST http://localhost:8000/api/auth/cookie-auth
```

The browser will open to YouTube Music. You need to:
1. Log in to YouTube Music
2. Open DevTools (F12)
3. Go to Network tab
4. Refresh page
5. Find `/browse` request
6. Copy as cURL
7. Paste in terminal

This is manual but works without any developer setup.

## Fixing Current Issues

### Issue: "Error: ENOENT: no such file or directory, stat 'E:\...\app\dist\index.html'"

**Solution**: Build the frontend first:
```bash
cd app
npm run build
npm run serve
```

### Issue: Tauri Configuration Error

**Solution**: Use the corrected `tauri.conf.json`:
```json
{
  "productName": "AMP",
  "version": "0.1.0",
  "tauri": {
    "allowlist": {
      "shell": {
        "open": true
      },
      "http": {
        "request": true
      }
    },
    "bundle": {
      "identifier": "com.amp.music"
    }
  }
}
```

### Issue: "Auth flow is not fully automated"

**Solution**: This is by design. YouTube requires authentication. Either:
- Use OAuth with your credentials (recommended, automated)
- Use cookie-based auth (manual, no credentials needed)

There is NO third option for fully automated YouTube auth without credentials.

## Summary Table

| Method | Your Setup | User Experience | Automation |
|--------|------------|----------------|------------|
| OAuth | ✅ Create credentials once | ✅ Click login, browser opens, done | ✅ Fully automated |
| Cookie-based | ❌ No setup | ⚠️ Manual header copy | ❌ Manual step |

## Recommended Approach

**Use OAuth with your credentials** (Option 1):
- You create credentials once
- Users get seamless, automated auth
- Industry standard approach
- Works like Spotify, etc.

## Need Help Creating OAuth Credentials?

If you're having trouble creating the Google OAuth credentials, I can guide you through it step-by-step. The process takes about 5 minutes and only needs to be done once.

Would you like me to:
1. Create a detailed step-by-step guide with screenshots?
2. Help you troubleshoot your current setup?
3. Continue with the cookie-based auth for now?

## Testing Your Setup

Once you've added your OAuth credentials to `.env`, test with:

```bash
# Test OAuth URL generation
curl -X POST http://localhost:8000/api/auth/login

# Check if credentials are loaded
curl http://localhost:8000/api/auth/status
```

Expected response should show `"client_configured": true`.
