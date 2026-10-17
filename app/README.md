# AMP Web Interface

React-based web interface for AMP (Another Music Player), built with Vite and TypeScript.

---

## Overview

This is the frontend for AMP. It can run in two modes:

1. **Web interface** (development/testing): Vite dev server at http://localhost:1420
2. **Tauri desktop app** (production): Wrapped in a native window (requires Rust build tools)

---

## Quick Start (Web Interface)

```bash
cd app
npm install    # First time only
npm run dev
```

Open **http://localhost:1420**

You also need the backend running:

```bash
# In another terminal, from project root
python amp/backend/main.py
```

---

## Features

- **Connect YouTube Music**: Cookie-based auth via browser import or Tauri sign-in window
- **Auth status display**: Shows signed_out / signed_in / expired state
- **Liked songs**: Displays your liked songs after authentication
- **Clean, modern UI**: Responsive design

---

## Project Structure

```
app/
├── src/                        # React/TypeScript source
│   ├── App.tsx                 # Main application component
│   ├── main.tsx                # Application entry point
│   ├── useYouTubeAuth.ts       # Auth React hook (state management)
│   └── index.css               # Global styles
├── src-tauri/                  # Tauri desktop app (structure ready)
│   ├── src/
│   │   ├── main.rs             # Tauri entry point
│   │   └── youtube_login.rs    # Google sign-in window command
│   ├── Cargo.toml              # Rust dependencies
│   ├── tauri.conf.json         # Tauri configuration
│   └── build.rs                # Tauri build script
├── public/                     # Static assets
├── icons/                      # Application icons
├── package.json                # Node.js dependencies and scripts
├── vite.config.ts              # Vite configuration
└── dev-server.cjs              # Proxy server for production-like testing
```

---

## Authentication Flow

AMP uses **cookie-based authentication** with YouTube Music (no OAuth credentials needed).

### In the web interface:

1. Click **"Connect YouTube Music"**
2. Choose **"Import from Firefox"** (or another browser)
3. The backend extracts cookies via yt-dlp
4. You're connected! Liked songs appear automatically.

### Via Tauri desktop app (when built):

1. Click **"Connect YouTube Music"**
2. A Google sign-in window opens
3. Sign in (including 2FA)
4. Tauri captures cookies and sends them to the backend

### Auth states:

| State | Meaning | UI |
|-------|---------|-----|
| `signed_out` | Not connected | Shows "Connect" button |
| `signed_in` | Connected | Shows account name + liked songs |
| `expired` | Session died | Shows "Session expired - reconnect" |

---

## The `useYouTubeAuth` Hook

`app/src/useYouTubeAuth.ts` manages all auth state:

```typescript
import { useYouTubeAuth } from './useYouTubeAuth';

function MyComponent() {
  const {
    status,           // 'signed_out' | 'signed_in' | 'expired'
    busy,             // true during auth operations
    error,            // error message if any
    account,          // { name, channelId } when signed in
    login,            // () => opens Tauri sign-in window
    logout,           // () => clears session
    importFromBrowser // (browser: string) => imports from browser
  } = useYouTubeAuth();
}
```

---

## Backend Integration

The frontend communicates with the backend via HTTP:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/auth/status` | Check auth status |
| POST | `/api/auth/cookies` | Submit cookies from Tauri window |
| POST | `/api/auth/import-browser` | Import cookies from browser |
| POST | `/api/auth/logout` | Clear session |
| GET | `/api/user/likes` | Get liked songs |
| GET | `/api/search?q={query}` | Search YouTube Music |

The Vite dev server proxies `/api/*` requests to `http://localhost:8000`.

---

## Scripts

| Script | Description |
|--------|-------------|
| `npm run dev` | Start Vite dev server (http://localhost:1420) |
| `npm run build` | Build for production (outputs to `dist/`) |
| `npm run preview` | Preview production build |
| `npm run serve` | Serve production build with API proxy (port 3000) |
| `npm run tauri:dev` | Run Tauri desktop app (requires Rust) |
| `npm run tauri:build` | Build Tauri desktop app (requires Rust) |

---

## Tauri Desktop App

The Tauri project structure is ready in `src-tauri/`. To build it, you need:

- **Rust 1.70+**
- **Visual Studio Build Tools** with C++ workload (Windows)
- **WebView2** (Windows, usually pre-installed)

```bash
cd app
npm run tauri:dev     # Development
npm run tauri:build   # Production build
```

> **Note**: The Tauri build is currently blocked on Windows due to missing Visual Studio Build Tools. The web interface (`npm run dev`) works without Tauri.

---

## Configuration

| Setting | Value |
|---------|-------|
| Dev server port | 1420 |
| Backend URL | http://localhost:8000 (proxied) |
| Production serve port | 3000 |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `npm install` fails | Ensure Node.js 18+ is installed |
| Can't connect to backend | Make sure `python amp/backend/main.py` is running |
| Auth import fails with Chrome | Use Firefox: `{"browser": "firefox"}` |
| Tauri build fails | Install Visual Studio Build Tools with C++ workload |
| Port 1420 in use | Kill the process or change port in `vite.config.ts` |

---

## License

MIT
