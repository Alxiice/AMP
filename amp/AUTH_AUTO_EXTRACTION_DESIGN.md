# Automatic Cookie Extraction Design

## Problem

Users must manually copy the Cookie header from browser DevTools and paste it into the app. This is cumbersome and error-prone.

## Solution: Tauri WebView Cookie Interception

The **recommended and working solution** is to use Tauri's webview API to:
1. Open a YouTube Music sign-in window directly in a Tauri webview
2. Use Tauri's `Webview::cookies_for_url()` to read cookies directly from that webview
3. Send the cookies to the backend

This approach:
- ✅ Works reliably with Chrome, Edge, Firefox, Brave, etc.
- ✅ No manual copy-paste required
- ✅ No external browser needed
- ✅ Uses Tauri's built-in webview with direct cookie access
- ✅ One-click sign-in experience

## Implementation

### Backend Changes

1. **New endpoint in `auth_routes.py`**:
   - `POST /api/auth/tauri-cookies` - Accepts cookies from Tauri webview

2. **No polling needed** - The cookies come directly from Tauri after the user signs in

### Frontend Changes

1. **New file `tauri_auth.ts`**:
   - `youtubeLogin()` - Calls Tauri command to open sign-in window
   - `isTauriAvailable()` - Checks if running in Tauri
   - `mightBeTauri()` - Synchronous check for UI rendering

2. **Updated `Auth.tsx`**:
   - "Sign In with YouTube (Tauri)" button (recommended method)
   - Falls back to browser polling method if Tauri not available
   - Clear user feedback

### Rust/Tauri Changes

1. **New file `youtube_login.rs`**:
   - `youtube_login()` Tauri command
   - Opens webview window to Google sign-in page
   - Waits for `__Secure-3PAPISID` cookie to appear
   - Returns cookies to frontend
   - Handles cancellation and timeout

2. **Updated `main.rs`**:
   - Includes `youtube_login` module
   - Registers the command handler

3. **Updated `Cargo.toml`**:
   - Adds `tokio = { version = "1", features = ["time"] }` dependency

## How It Works

### Tauri WebView Flow (Recommended)

```
┌─────────────────────────────────────────────────────────────┐
│                    User Clicks "Sign In"                      │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Frontend calls youtubeLogin()                    │
│              (tauri_auth.ts)                                  │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Tauri opens webview window                         │
│              (youtube_login.rs)                                │
│              - URL: Google sign-in page                         │
│              - Incognito: true (clean session)                 │
│              - User Agent: Desktop Chrome                      │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              User completes Google sign-in                     │
│              in the webview window                              │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Tauri polls webview.cookies_for_url()            │
│              every 800ms for __Secure-3PAPISID cookie          │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Cookie found! Wait 1.5s for redirect chain        │
│              to complete, then read all cookies                 │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Close webview, return cookies to frontend        │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Frontend calls POST /api/auth/tauri-cookies       │
│              with the cookies                                     │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Backend saves cookies, updates auth state          │
│              User is now authenticated!                           │
└─────────────────────────────────────────────────────────────┘
```

### Fallback: Browser Polling Flow

If Tauri is not available (e.g., running in plain browser for development), the app falls back to:

1. Open default browser to YouTube Music
2. Poll the browser's cookie store every 5 seconds using yt-dlp
3. Detect when auth cookies appear
4. Import them automatically

**Limitation**: Firefox must be closed during this process (profile DB lock).

## Files Modified

### Backend
- `backend/api/auth_routes.py` - Added `/tauri-cookies` endpoint
- `backend/services/signin_flow.py` - Background polling service (fallback)

### Frontend
- `frontend/src/api.ts` - Added `TauriCookie` type and `setTauriCookies()` method
- `frontend/src/tauri_auth.ts` - Tauri-specific auth functions (NEW)
- `frontend/src/pages/Auth.tsx` - Updated UI with Tauri and fallback methods
- `frontend/src/styles.css` - Added auth flow status styles

### Tauri/Rust
- `frontend/src-tauri/Cargo.toml` - Added tokio dependency
- `frontend/src-tauri/src/youtube_login.rs` - Tauri command for webview sign-in (NEW)
- `frontend/src-tauri/src/main.rs` - Updated to include youtube_login module

## Fallback Methods

If both Tauri webview and browser polling fail, users can still use:

1. **Manual Cookie Paste** (existing)
   - Copy Cookie header from browser DevTools
   - Paste into textarea
   - Click "Set Cookies"

2. **Browser Import** (existing)
   - Select browser from dropdown
   - Click "Import from [browser]"
   - Firefox must be closed

## Testing

### Tauri WebView Method
```bash
# Run Tauri dev
cd /e/Documents/TRAVAIL/packages/AMP2/amp/frontend
npm run tauri dev

# In the app:
# 1. Go to Auth page
# 2. Click "Sign In with YouTube (Tauri)"
# 3. Sign in to YouTube Music in the pop-up window
# 4. Cookies are automatically imported
```

### Browser Polling Method (Fallback)
```bash
# Start backend
cd /e/Documents/TRAVAIL/packages/AMP2/amp
python -m backend.main --debug

# In a browser, go to http://localhost:1420
# 1. Go to Auth page
# 2. Click "Sign In with YouTube (Browser Polling)"
# 3. Browser opens to YouTube Music
# 4. Sign in
# 5. Backend polls and auto-imports cookies (except Firefox must be closed)
```

## Known Issues

1. **Tauri WebView on Linux**: May require additional configuration for some browsers
2. **Firefox with Browser Polling**: Must be closed before starting the flow
3. **Chrome/Edge v127+**: yt-dlp may have difficulty reading encrypted cookies

## Recommendation

**Use Tauri WebView method** - it's the most reliable and provides the best user experience.

The browser polling method is kept as a fallback for development/testing without Tauri, but the Tauri webview method should be the primary way users sign in.
