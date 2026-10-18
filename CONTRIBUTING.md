# Contributing to AMP

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Backend (FastAPI) |
| Node.js | 20+ | Frontend (React + Vite) |
| Rust | 1.70+ | Tauri desktop app (build only) |
| Git | any | Version control |

## Quick Start

### 1. Clone & Setup

```bash
git clone <repo-url>
cd AMP

# Python virtual environment (already created)
# Windows CMD:
activate.bat
# Windows PowerShell:
.\activate.ps1
# WSL/Linux:
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd app
npm install
cd ..
```

### 2. Run the Backend

```bash
# From the AMP/ root directory
python amp/backend/main.py
# Backend runs at http://localhost:8000
# API docs at http://localhost:8000/docs
```

### 3. Run the Frontend (Web Mode)

```bash
cd app
npm run dev
# Frontend runs at http://localhost:1420
```

Open http://localhost:1420 in your browser. The app auto-detects the backend at `http://localhost:8000`.

### 4. Run Tests

```bash
cd amp
../venv/Scripts/python.exe -m pytest backend/tests/ -v
# Or on WSL/Linux:
../venv/bin/python -m pytest backend/tests/ -v
```

---

## Running the Tauri Desktop App

### Option A: Native Windows (Recommended)

Build and run the desktop app directly on Windows. This avoids all WSL2 networking issues.

**Prerequisites:**
- [Visual Studio Build Tools](https://visualstudio.microsoft.com/downloads/) with **"Desktop development with C++"** workload
- [WebView2](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) (pre-installed on Windows 11)
- [Rust](https://rustup.rs/) (installs via `rustup`)

```powershell
# From the AMP/app directory
npm run tauri:dev     # Development mode (hot reload)
npm run tauri:build   # Production build (.exe in src-tauri/target/release/)
```

### Option B: Cross-compile Windows .exe from WSL2 (no Windows dev tools needed)

Build a Windows `.exe` inside WSL2 using the `mingw-w64` cross-compiler, then copy
it to Windows and run it from PowerShell. **No Visual Studio, Rust, or Node.js needed on Windows.**

#### Step 1: Install cross-compilation tools in WSL2

```bash
# Open a WSL2 terminal (Ubuntu/Debian)
sudo apt update
sudo apt install -y mingw-w64

# Add the Windows GNU Rust target
rustup target add x86_64-pc-windows-gnu
```

#### Step 2: Build the frontend

```bash
cd /mnt/e/Documents/TRAVAIL/packages/AMP/app
npm install
npm run build
# Output goes to AMP/dist/ (configured in vite.config.ts)
```

#### Step 3: Build the Windows .exe

A `.cargo/config.toml` is already configured in `app/src-tauri/` to use the mingw linker.

```bash
cd /mnt/e/Documents/TRAVAIL/packages/AMP/app/src-tauri
cargo build --target x86_64-pc-windows-gnu --release
```

Or using the Tauri CLI (builds frontend + exe in one step):
```bash
cd /mnt/e/Documents/TRAVAIL/packages/AMP/app
npm run tauri:build -- --target x86_64-pc-windows-gnu
```

#### Step 4: Copy the .exe to Windows and run it

The exe is at:
```
app/src-tauri/target/x86_64-pc-windows-gnu/release/app.exe
```

Copy it to Windows (e.g., your Desktop) and launch from PowerShell:
```powershell
& "$env:USERPROFILE\Desktop\app.exe"
```

#### Step 5: Start the backend on Windows

The exe runs natively on Windows, so it connects to `http://127.0.0.1:8000`.
Start the backend in a separate PowerShell window:

```powershell
cd E:\Documents\TRAVAIL\packages\AMP
.\venv\Scripts\activate.ps1
python amp\backend\main.py
```

#### Requirements on the Windows machine

- Windows 10/11 with **WebView2** runtime (pre-installed on Windows 11; [download here](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) for Windows 10)
- No Visual Studio, no Rust, no Node.js needed on Windows

#### Troubleshooting cross-compilation

| Error | Solution |
|-------|----------|
| `linker x86_64-w64-mingw32-gcc not found` | `sudo apt install mingw-w64` |
| `failed to run custom build command for tauri-winres` | Make sure `app/src-tauri/icons/32x32.png` exists |
| Build succeeds but exe won't start | Install WebView2 runtime on Windows |
| `gobject-2.0 not found` (building for Linux) | `sudo apt install libglib2.0-dev libgtk-3-dev libsoup-3.0-dev libjavascriptcoregtk-4.1-dev` |
| `libappindicator3-dev` conflict on Ubuntu 24.04+ | Install only `libayatana-appindicator3-dev` |

### Option C: Run Tauri in WSL2 (dev only, needs display)

For development only — run the Tauri app inside WSL2 with a display.

#### Networking: Backend on Windows, App in WSL2

When the Tauri app runs inside WSL2, `127.0.0.1` refers to the WSL2 VM, **not** Windows.
The backend running on Windows is unreachable at `localhost:8000`.

**Solution:** The app auto-detects the Windows host IP via a Tauri command (`get_wsl_host_ip`)
that reads `/etc/resolv.conf`. The first nameserver is the WSL2 gateway (= Windows host IP).

If auto-detection fails, set the API URL manually in the app's **Settings** panel:

```
http://<windows-host-ip>:8000
```

Find your Windows host IP:
```bash
# In WSL2 terminal:
cat /etc/resolv.conf | grep nameserver | awk '{print $2}'
# Example output: 10.255.255.254
```

#### WSL2 System Dependencies (for Linux build)

```bash
sudo apt update
sudo apt install -y libwebkit2gtk-4.1-dev \
    build-essential \
    curl \
    wget \
    file \
    libssl-dev \
    libgtk-3-dev \
    libayatana-appindicator3-dev \
    librsvg2-dev \
    libglib2.0-dev \
    libsoup-3.0-dev \
    libjavascriptcoregtk-4.1-dev \
    pkg-config
```

#### Building in WSL2 (Linux binary)

```bash
cd /mnt/e/Documents/TRAVAIL/packages/AMP/app
npm install
npm run tauri:dev     # Dev mode (needs a display: use WSLg or VcXsrv)
```

#### WSL2 Display

WSL2 needs a display for GUI apps. Options:
- **WSLg** (Windows 11 22H2+): built-in, just run `npm run tauri:dev`
- **VcXsrv**: install on Windows, set `DISPLAY` in WSL2:
  ```bash
  export DISPLAY=$(cat /etc/resolv.conf | grep nameserver | awk '{print $2}'):0
  ```

---

## Project Structure

```
AMP/
├── amp/                    # Python backend
│   └── backend/
│       ├── api/            # FastAPI routes
│       │   ├── server.py   # App setup, CORS, router registration
│       │   ├── endpoints.py # Main API endpoints (/api/*)
│       │   └── auth_routes.py # Auth endpoints (/api/auth/*)
│       ├── services/       # Business logic
│       │   ├── auth.py     # Cookie-based YouTube auth
│       │   ├── youtube.py  # ytmusicapi wrapper
│       │   └── streaming.py # yt-dlp audio streaming
│       ├── database/       # SQLAlchemy models & sessions
│       ├── config.py       # Settings (Pydantic)
│       ├── main.py         # Entry point
│       └── tests/          # 92 tests
├── app/                    # React frontend + Tauri
│   ├── src/
│   │   ├── App.tsx         # Main UI
│   │   └── useYouTubeAuth.ts # Auth hook + API client
│   └── src-tauri/          # Tauri Rust backend
│       ├── .cargo/
│       │   └── config.toml # Cross-compilation linker config
│       ├── src/
│       │   ├── main.rs     # Tauri entry + command registration
│       │   ├── youtube_login.rs # Sign-in window command
│       │   └── wsl_detect.rs    # WSL2 host IP detection
│       ├── capabilities/   # Tauri 2.x permissions
│       ├── icons/          # App icons
│       └── tauri.conf.json
├── dist/                   # Frontend build output (Vite)
├── venv/                   # Python virtual environment
├── AGENTS.md               # AI agent instructions
├── ROADMAP.md              # 10-phase roadmap
├── IMPLEMENTATION_NOTES.md # Phase 1 & 2 details
└── CONTRIBUTING.md         # This file
```

## Development Workflow

1. **Read first**: Check `AGENTS.md` for current phase and `ROADMAP.md` for next steps
2. **Branch**: Create a feature branch from `develop`
3. **Code**: Follow existing patterns, add tests for new functionality
4. **Test**: `cd amp && ../venv/Scripts/python.exe -m pytest backend/tests/ -v`
5. **Build**: `cd app && npm run build` (verify frontend compiles)
6. **Commit**: Small, atomic commits with clear messages
7. **Update**: Update `AGENTS.md` with progress

## Authentication Flow (for context)

The app uses **cookie-based auth** (not OAuth — YouTube Music's private API rejects OAuth tokens).

1. **Primary**: Tauri sign-in window → user logs in → cookies captured from webview → sent to backend
2. **Web mode**: Browser tab opens to music.youtube.com → user signs in → yt-dlp imports cookies from browser
3. **Fallback**: Quick import from an already-signed-in browser (Firefox recommended)

Cookies are saved to `.amp/cache/ytm_session.json` with `0600` permissions.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `npm run tauri:dev` fails with "Missing script" | Run `npm install` in `app/` first |
| Tauri build fails: "no targets specified" | `Cargo.toml` must be in `app/src-tauri/`, not `app/` |
| Tauri 2.x: "Cannot read properties of undefined (reading 'invoke')" | Add `@tauri-apps/api` to `app/package.json` dependencies and create `capabilities/default.json` |
| WSL2: "Backend unreachable" | Set API URL to Windows host IP (see Option C above) |
| WSL2: "Load failed" / blank window | Install WSLg or VcXsrv for display |
| WSL2: `gobject-2.0 not found` | `sudo apt install libglib2.0-dev libgtk-3-dev libsoup-3.0-dev libjavascriptcoregtk-4.1-dev` |
| `webbrowser.open()` fails on backend | The `/auth/open-signin` endpoint now returns the URL for manual opening |
| Tests fail: SQLite QueuePool timeout | Pre-existing flaky test, re-run to confirm |
| Exe shows blank screen / ERR_CONNECTION_REFUSED | `frontendDist` path was wrong — fixed to `../../dist` in tauri.conf.json |
| Cross-compile: linker not found | `sudo apt install mingw-w64` in WSL2 |
| Exe won't start on Windows | Install WebView2 runtime |

## Coding Guidelines

- **Read before editing**: Always read files before making changes
- **Match existing style**: Indentation, naming, error handling density
- **Write tests**: Add tests for all new backend functionality
- **Minimal diffs**: Don't touch what wasn't asked
- **CRLF line endings**: The project uses CRLF on Windows; preserve them
- **No emoji**: In code, comments, or commit messages
