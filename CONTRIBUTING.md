# Contributing to AMP

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Backend (FastAPI) |
| Node.js | 20+ | Frontend (React + Vite) |
| Rust | 1.70+ | Tauri desktop app (build only) |
| Git | any | Version control |

---

## Branch Strategy

We follow a structured branching workflow with the following hierarchy:

```
master (stable, production-ready, tested and working)
    ↓
develop (integration branch for current phase, testing in progress)
    ↓
feature/xxx, fix/xxx, chore/xxx, refactor/xxx, docs/xxx (working branches)
```

### Branch Types and Naming Conventions

| Type | Prefix | Example | Purpose |
|------|--------|---------|---------|
| Feature | `feat/` | `feat/youtube-search` | New functionality |
| Bug Fix | `fix/` | `fix/auth-cookie-import` | Bug fixes |
| Chore | `chore/` | `chore/update-deps` | Maintenance tasks (no functional change) |
| Refactor | `refactor/` | `refactor/streaming-service` | Code restructuring |
| Documentation | `docs/` | `docs/update-readme` | Documentation updates |

### Workflow Rules

1. **master**: Protected branch. Only merges from `develop` via Pull Request. Represents stable, tested, production-ready code.
2. **develop**: Integration branch for the current phase. All feature/fix branches merge here first for testing.
3. **Feature/Fix branches**: Always branch from `develop`. Never branch from `master` directly.
4. **Direct commits**: Exceptionally allowed on `develop` for meta-changes (CI/CD, linter config, documentation updates).

### Standard Workflow

```bash
# Start a new feature
git checkout develop
git pull origin develop
git checkout -b feat/your-feature-name

# Make changes, commit
git add .
git commit -m "feat: description of your feature"

# Push and create PR to develop
git push origin feat/your-feature-name
# Then create PR: feat/your-feature-name -> develop

# After PR is approved and merged to develop, it will eventually be merged to master
```

---

## Quality Gates

### 1. Linting with Ruff

All Python code must pass [Ruff](https://docs.astral.sh/ruff/) linting before commit.

**Install Ruff:**
```bash
pip install ruff
```

**Run linting:**
```bash
# From AMP/ root
ruff check amp/backend/
```

**Fix automatically:**
```bash
ruff check --fix amp/backend/
```

**Configuration**: See `.ruff.toml` for rules.

**Pre-commit hook (recommended):**
```bash
# Install pre-commit
pip install pre-commit

# Create .pre-commit-config.yaml in AMP/
cat > .pre-commit-config.yaml << 'EOF'
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.0
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
EOF

# Enable pre-commit
pre-commit install
```

### 2. Testing with pytest

All code changes must maintain or increase test coverage. Tests must pass before merging.

**Run tests:**
```bash
cd amp
../venv/Scripts/python.exe -m pytest backend/tests/ -v
```

**Run tests with coverage:**
```bash
cd amp
../venv/Scripts/python.exe -m pytest backend/tests/ --cov=backend --cov-report=term-missing -v
```

**Coverage Requirements:**
- New code must have test coverage (>= 80% recommended)
- Any PR that decreases overall coverage must include a justification
- Coverage reports are generated automatically in CI/CD

### 3. Code Coverage

**Minimum Coverage**: 80% ( tracked via pytest-cov)

**View coverage report:**
```bash
cd amp
../venv/Scripts/python.exe -m pytest backend/tests/ --cov=backend --cov-report=html
# Opens HTML report in browser
```

**Coverage configuration** is in `.coveragerc`.

---

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

# Install backend dependencies with dev tools
cd amp
pip install -r backend/requirements.txt
cd ..

# Install Ruff linter
pip install ruff

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

### 5. Run Linting

```bash
ruff check amp/backend/
```

### 6. Run Tests with Coverage

```bash
cd amp
../venv/Scripts/python.exe -m pytest backend/tests/ --cov=backend --cov-report=term-missing -v
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

> **Important:** WSL2 cannot write build artifacts to `/mnt/e/` (Windows drive mount).
> Redirect the target directory to the WSL2 filesystem with `CARGO_TARGET_DIR`.

```bash
# Redirect build output to WSL2 native filesystem (avoids /mnt/e permission errors)
export CARGO_TARGET_DIR=/tmp/amp-build

cd /mnt/e/Documents/TRAVAIL/packages/AMP/app/src-tauri
cargo build --target x86_64-pc-windows-gnu --release
```

Or using the Tauri CLI (builds frontend + exe in one step):
```bash
export CARGO_TARGET_DIR=/tmp/amp-build
cd /mnt/e/Documents/TRAVAIL/packages/AMP/app
npm run tauri:build -- --target x86_64-pc-windows-gnu
```

#### Step 4: Copy the .exe to Windows and run it

The exe is at:
```
/tmp/amp-build/x86_64-pc-windows-gnu/release/app.exe
```

Copy it to Windows (e.g., your Desktop):
```bash
# In WSL2:
cp -R /tmp/amp-build/x86_64-pc-windows-gnu/release /mnt/e/Documents/TRAVAIL/packages/AMP/build
```

Then launch from PowerShell:
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
| `Permission denied (os error 13)` on `/mnt/e/` | `export CARGO_TARGET_DIR=/tmp/amp-build` before building |
| `failed to run custom build command for tauri-winres` | Make sure `app/src-tauri/icons/32x32.png` exists |
| Build succeeds but exe won't start | Install WebView2 runtime on Windows |

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
├── .github/
│   └── workflows/
│       └── python-ci.yml      # GitHub Actions: pytest + Ruff
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
│       └── tests/          # pytest tests
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
├── pytest.ini              # pytest configuration with coverage
├── .ruff.toml              # Ruff linter configuration
├── AGENTS.md               # AI agent instructions
├── ROADMAP.md              # 10-phase roadmap
├── IMPLEMENTATION_NOTES.md # Phase 1 & 2 details
└── CONTRIBUTING.md         # This file
```

---

## Development Workflow

### Before Starting

1. **Read first**: Check `AGENTS.md` for current phase and `ROADMAP.md` for next steps
2. **Check branch strategy**: See [Branch Strategy](#branch-strategy) above
3. **Update dependencies**: Run `git pull` and install new requirements

### Standard Process

1. **Branch**: Create a feature/fix branch from `develop`
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feat/your-feature-name
   ```

2. **Code**: Follow existing patterns and [Coding Guidelines](#coding-guidelines)

3. **Lint**: Run Ruff linter
   ```bash
   ruff check amp/backend/ --fix
   ```

4. **Test**: Run tests with coverage
   ```bash
   cd amp
   ../venv/Scripts/python.exe -m pytest backend/tests/ --cov=backend --cov-report=term-missing -v
   ```

5. **Verify Coverage**: Ensure coverage is maintained or increased
   ```bash
   cd amp
   ../venv/Scripts/python.exe -m pytest backend/tests/ --cov=backend --cov-report=html
   # Open htmlcov/index.html in browser
   ```

6. **Commit**: Small, atomic commits with clear messages
   ```bash
   git add .
   git commit -m "feat: description of changes"
   ```

7. **Push and PR**: Push branch and create PR to `develop`
   ```bash
   git push origin feat/your-feature-name
   # Then create PR: feat/your-feature-name -> develop
   ```

8. **Update**: Update `AGENTS.md` with progress after PR is merged

### For Direct Commits to develop (Meta-changes only)

Exceptionally, the following changes can be committed directly to `develop`:
- CI/CD configuration updates
- Linter configuration updates
- Documentation updates
- Dependency updates
- Test infrastructure changes

```bash
# For meta-changes only
git checkout develop
git pull origin develop
# Make your changes
ruff check amp/backend/  # Verify linting passes
cd amp
../venv/Scripts/python.exe -m pytest backend/tests/ -v  # Verify tests pass
git add .
git commit -m "chore: update CI/CD configuration"
git push origin develop
```

---

## GitHub Actions CI/CD Setup

The project uses GitHub Actions for automated testing and linting on every push and PR.

### Workflow File Location

```
.github/workflows/python-ci.yml
```

### What the Workflow Does

1. **On Push to any branch**: Runs linting and tests
2. **On Pull Request**: Runs linting and tests, reports coverage
3. **Coverage**: Generates coverage report and uploads to GitHub

### Creating the Workflow

The workflow file `.github/workflows/python-ci.yml` is already created with:
- Python 3.11 testing
- Ruff linting
- pytest with coverage
- Artifact upload
- Codecov integration (optional)

### Steps to Enable GitHub Testing

1. **Push the workflow file**:
   ```bash
   git add .github/workflows/python-ci.yml
   git commit -m "ci: add GitHub Actions workflow for pytest and Ruff"
   git push origin develop
   ```

2. **Verify workflow runs**:
   - Go to your GitHub repository
   - Click on "Actions" tab
   - The workflow should automatically run on the next push
   - Check the logs to ensure tests pass and linting succeeds

3. **Optional: Add Codecov integration** (for coverage tracking):
   - Go to [codecov.io](https://codecov.io/) and sign in with GitHub
   - Add your repository
   - Get your CODECOV_TOKEN from Codecov settings
   - Add it to GitHub repository secrets:
     - Settings → Secrets and variables → Actions → New repository secret
     - Name: `CODECOV_TOKEN`
     - Value: `your-codecov-token`

4. **Optional: Protect branches**:
   - Go to Settings → Branches → Branch protection rules
   - Add rule for `master`:
     - Require status checks to pass
     - Require pull request reviews
     - Include administrators
   - Add rule for `develop`:
     - Require status checks to pass

### Workflow Badges

Add these to your README.md:

```markdown
![Python CI](https://github.com/your-org/AMP/actions/workflows/python-ci.yml/badge.svg)
![Code Coverage](https://img.shields.io/codecov/c/github/your-org/AMP/develop?logo=codecov)
```

---

## Authentication Flow (for context)

The app uses **cookie-based auth** (not OAuth — YouTube Music's private API rejects OAuth tokens).

1. **Primary**: Tauri sign-in window → user logs in → cookies captured from webview → sent to backend
2. **Web mode**: Browser tab opens to music.youtube.com → user signs in → yt-dlp imports cookies from browser
3. **Fallback**: Quick import from an already-signed-in browser (Firefox recommended)

Cookies are saved to `.amp/cache/ytm_session.json` with `0600` permissions.

---

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
| Cross-compile: linker not found | `sudo apt install mingw-w64` |
| Cross-compile: "Permission denied" on /mnt/e | `export CARGO_TARGET_DIR=/tmp/amp-build` before building |
| Exe won't start on Windows | Install WebView2 runtime |

---

## Coding Guidelines

### General Rules

- **Read before editing**: Always read files before making changes
- **Match existing style**: Indentation, naming, error handling density
- **Write tests**: Add tests for all new backend functionality
- **Minimal diffs**: Don't touch what wasn't asked
- **CRLF line endings**: The project uses CRLF on Windows; preserve them
- **No emoji**: In code, comments, or commit messages

### Code Quality Checklist

Before creating a PR, verify:

- [ ] All tests pass (`pytest backend/tests/ -v`)
- [ ] Linting passes (`ruff check amp/backend/`)
- [ ] Coverage is maintained or increased
- [ ] New code has corresponding tests
- [ ] Documentation is updated (if applicable)
- [ ] Branch follows naming convention (feat/ fix/ chore/ etc.)
- [ ] Commits are atomic with clear messages
