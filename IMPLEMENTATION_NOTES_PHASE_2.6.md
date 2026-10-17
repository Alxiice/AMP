# AMP - Phase 2.6 Implementation Notes: Web Interface Foundation

> **Phase**: 2.6 (Web Interface Foundation)
> **Status**: ✅ COMPLETE
> **Date**: 2026-10-17
> **Branch**: `fix/auth`

---

## 📌 Executive Summary

Phase 2.6 created a **React web interface** for AMP that runs in a browser via Vite dev server, enabling development and testing without the Tauri desktop app. The Tauri build was blocked on Windows due to missing Visual Studio Build Tools (C++ workload), so the web interface provides an immediate way to test the auth flow and UI.

**Result**: A working web interface at http://localhost:1420 with auth UI, liked songs display, and a React hook for auth state management. The Tauri project structure is also fixed and ready for when build tools are available.

---

## 🎯 Problem Statement

1. **Tauri build blocked**: `npm run tauri:dev` failed with `cargo metadata` errors — the Tauri project structure was wrong (Cargo.toml and tauri.conf.json in wrong locations, missing `src/main.rs`).
2. **No way to test the UI**: Without a working frontend, the auth flow couldn't be tested manually.
3. **Need for rapid iteration**: Building a Tauri app for every UI change is slow. A web interface enables fast iteration.

---

## 🏗️ Solution Architecture

### Web Interface (Primary)

```
┌─────────────────────────────────────────┐
│  Browser: http://localhost:1420          │
│  ┌─────────────────────────────────┐    │
│  │  React App (Vite dev server)     │    │
│  │  ├── App.tsx                     │    │
│  │  ├── useYouTubeAuth.ts (hook)    │    │
│  │  └── index.css                   │    │
│  └─────────────────────────────────┘    │
│         │                                │
│         │ /api/* proxied                 │
│         ▼                                │
│  http://localhost:8000 (FastAPI)         │
└─────────────────────────────────────────┘
```

### Tauri Desktop App (Structure Ready, Build Blocked)

```
app/src-tauri/
├── src/
│   ├── main.rs              # Tauri entry point
│   └── youtube_login.rs     # Google sign-in window command
├── Cargo.toml               # Rust dependencies
├── tauri.conf.json          # Tauri 2.x configuration
└── build.rs                 # Tauri build script
```

---

## 📊 Files Changed

### New Files
| File | Purpose |
|------|---------|
| `app/src/useYouTubeAuth.ts` | React hook for auth state management (status, login, logout, importFromBrowser) |
| `app/src-tauri/Cargo.toml` | Rust dependencies (moved from `app/`, fixed) |
| `app/src-tauri/tauri.conf.json` | Tauri 2.x configuration (moved from `app/`) |
| `app/src-tauri/build.rs` | Tauri build script |
| `app/src-tauri/src/main.rs` | Tauri entry point (moved from `app/src-tauri/main.rs`) |

### Modified Files
| File | Changes |
|------|---------|
| `app/src/App.tsx` | Simplified to use `useYouTubeAuth` hook, removed manual auth flow handling |
| `app/package.json` | Updated scripts: `dev` (Vite on port 1420), `tauri:dev`, `tauri:build` |
| `app/vite.config.ts` | Configured proxy for `/api/*` → `http://localhost:8000`, port 1420 |

---

## 🔑 Key Design Decisions

### 1. Vite Dev Server (Not Tauri) for Development

The web interface uses Vite's dev server on **port 1420** with a proxy for `/api/*` requests to the backend on port 8000. This enables:
- Hot module replacement (instant UI updates)
- No Rust compilation needed
- Works on any platform with Node.js

### 2. `useYouTubeAuth` React Hook

Encapsulates all auth logic in a reusable hook:

```typescript
const { status, busy, error, account, login, logout, importFromBrowser } = useYouTubeAuth();
```

- Polls `/api/auth/status` on mount
- Handles `signed_out` / `signed_in` / `expired` states
- Provides `login()` (Tauri sign-in window) and `importFromBrowser(browser)` methods
- Manages loading and error states

### 3. Tauri Project Structure Fixed

Moved files to standard Tauri 2.x layout:
- `app/Cargo.toml` → `app/src-tauri/Cargo.toml`
- `app/tauri.conf.json` → `app/src-tauri/tauri.conf.json`
- `app/src-tauri/main.rs` → `app/src-tauri/src/main.rs`
- Created `app/src-tauri/build.rs`

### 4. Port 1420 (Not 5173)

Vite's default port 5173 might conflict with other projects. AMP uses **1420** for the dev server.

---

## 🧪 Testing

### Manual Testing

```bash
# Terminal 1: Backend
python amp/backend/main.py

# Terminal 2: Frontend
cd app
npm run dev
```

1. Open http://localhost:1420
2. Click "Connect YouTube Music"
3. Choose "Import from Firefox"
4. Verify liked songs appear

### Automated Tests

Backend tests still pass: **92/92**

```bash
pytest amp/backend/tests/ -v
```

---

## ⚠️ Known Limitations

1. **Tauri desktop app not buildable yet**: Requires Visual Studio Build Tools with C++ workload on Windows. The project structure is correct; only the build tools are missing.
2. **Sign-in window only works in Tauri**: The `login()` method in `useYouTubeAuth` calls `invoke("youtube_login")` which only works inside the Tauri app. In the web interface, use `importFromBrowser()` instead.
3. **CORS**: The backend has CORS enabled for development. For production, configure allowed origins.

---

## 🚀 Next Steps

- Install Visual Studio Build Tools to enable Tauri desktop builds
- Continue to **Phase 3: Core Playback System** (chunk caching, streaming endpoints)
- Add playback UI components to the web interface
