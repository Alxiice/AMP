# Phase 6 — App lifecycle & packaging

**Goal**: the Tauri app starts, owns and stops its backend, in dev and in the packaged build, on any OS. No orphaned processes and no fixed-port collisions. Data lives in a stable per-user directory. The packaged build runs without a checkout of the repo.

**Effort**: 1–2 days · **Depends on**: Phases 1 and 4 (and 5.6 if the auto token is wanted) · **Branch**: `fix/phase-6-lifecycle`

---

## 1. Problems addressed

| # | Problem | Where |
|---|---|---|
| F14 | `capabilities/default.json` grants `shell:allow-spawn` **without a scope**. Tauri v2 normally rejects spawning commands that aren't allow-listed, so the JS-side spawn very likely fails and the app silently adopts whatever backend is already on port 8000 (`_probeExistingBackend`). **Check this first** (6.0). | `default.json`, `sidecar.ts:66-104` |
| — | No kill on exit. The JS cleanup in `useEffect` doesn't run when the window closes, so the backend can outlive the app. The force-kill tooling in `app.py` and `amp_control.py` works around these orphans. | `App.tsx:36-38` |
| — | Venv path hard-coded to `venv/Scripts/python.exe` (Windows only); relative `cwd: "../"` | `sidecar.ts:38-42`, `:150` |
| — | Fixed port 8000 with no collision handling | everywhere |
| F16 | `config._project_root()` resolves from `__file__`. Under PyInstaller one-file, that's the **temp extraction dir**, so cache, logs, DB and credentials are lost on every launch (or written somewhere odd). | `config.py:17-20` |
| — | `externalBin: ["binaries/amp-backend"]` but there's no build step that produces `amp-backend-<target-triple>[.exe]`, the file name Tauri expects | `tauri.conf.json`, `amp-backend.spec` |
| — | Two overlapping launchers: `app.py` (1 517 lines) and `amp_control.py` (543 lines) | repo root |
| — | Log files never rotate | `logger.py` (`FileHandler`) |
| — | Deprecations: FastAPI `on_event`; `datetime.utcnow()` (Python 3.12+) | `server.py:81-93`, `models.py`, `streaming.py` |
| — | P7 (Windows encoding on subprocess pipes) is unhandled since the `encoding` spawn option was removed | `sidecar.ts:143` |

---

## 2. Target design

```
Tauri (Rust)                                    Backend (Python)
──────────────────────────────────────          ─────────────────────────────
setup():
  data_dir = app_data_dir()                     --data-dir <dir>  → settings.configure_paths()
  port     = pick_free_port()                   --port <port>
  token    = random (optional, 5.6)             --token <token>
  child    = spawn(dev: venv python | prod:     --parent-watch  (exit when stdin closes)
                   sidecar amp-backend)
  forward stdout/stderr → event "backend-log"
  manage(BackendState{child, port, token})
command backend_info() → {port, token}
on RunEvent::Exit → child.kill()
```

The frontend no longer spawns anything. `sidecar.ts` becomes a client: it calls `backend_info`, polls health, and listens to `backend-log` events. JS gets **no** shell permissions.

---

## 3. Tasks

### 6.0 Check the current spawn behaviour (15 min)

- With nothing on port 8000, run `npm run tauri dev`. Read the Logs page: does `Command.create(...).spawn()` succeed or fail with a scope error? Record the answer in AGENTS.md. Either way 6.1 replaces it, but the answer explains past "port already in use" reports.

### 6.1 Spawn and own the backend from Rust

Files: `src-tauri/src/main.rs`, new `src-tauri/src/backend.rs`

- In `Builder::setup`:
  - **Dev** (`cfg!(debug_assertions)`): resolve Python from the env var `AMP_PYTHON`, falling back to `<repo>/amp/venv/Scripts/python.exe` on Windows or `<repo>/amp/venv/bin/python` elsewhere. `<repo>` comes from `env!("CARGO_MANIFEST_DIR")/../..`. Use `app.shell().command(python).args(["-m", "backend.main", …]).current_dir(amp_dir)`.
  - **Prod**: `app.shell().sidecar("amp-backend")?.args([...])`.
  - Store the `CommandChild` in `app.manage(Mutex<BackendState>)`.
  - Forward `CommandEvent::Stdout/Stderr` lines, decoded with `String::from_utf8_lossy` (this covers P7), to the frontend with `app.emit("backend-log", line)`. On `CommandEvent::Terminated`, emit `backend-status: "stopped"`.
- `.build(...)` then `.run(|app, event| if let RunEvent::Exit = event { kill child })`.
- Commands: `backend_info() -> {port, token}`, `restart_backend()`.
- `capabilities/default.json`: remove `shell:allow-spawn` and `shell:allow-stdin-write`. Add only what the frontend needs (core events).

### 6.2 Free port + CSP

- `pick_free_port()`: bind `127.0.0.1:0`, read the port, drop the listener, pass `--port`. Use the env var `AMP_PORT` instead if it is set, which is useful for the dev tools.
- `api.ts`: `BASE_URL` is set once from `backend_info()` at startup. Outside Tauri (plain `npm run dev`), fall back to `http://127.0.0.1:8000`.
- CSP in `tauri.conf.json` and `index.html`: `connect-src` and `media-src` → `http://127.0.0.1:*`.
- Backend CORS and Host checks are unaffected (they don't depend on the port).

### 6.3 Backend exits with its parent

File: `amp/backend/main.py`

- `--parent-watch`: start a daemon thread that blocks on `sys.stdin.read()`. On EOF (the parent died and the pipe closed), call `os._exit(0)` after a best-effort `DownloadManager.stop()`. This works on all OSes with no extra dependencies. Rust keeps the child's stdin pipe open for the app's lifetime.
- Also write `<data_dir>/backend.pid`. On startup, if the file exists and that PID is a live AMP backend (`/api/health` on the recorded port answers `app: "AMP v2"`), log a WARNING. The control panel can use the same file.

### 6.4 Data directory

Files: `amp/backend/config.py`, `amp/backend/main.py`

- `--data-dir <path>` → `settings.configure_paths(data_dir=…, db_file=data_dir/"userdb.sqlite")` (the API from Phase 0).
- Rust passes `app.path().app_data_dir()` (e.g. `%APPDATA%\com.amp.v2\`).
- Without `--data-dir` (manual runs, tests, the control panel), keep today's `amp/.amp/` and `amp/userdb.sqlite`.
- One-time convenience: if the app data dir is empty and `amp/.amp/cache/ytm_session.json` exists **in dev**, log a hint. **Don't copy credentials automatically.**

### 6.5 Build the sidecar binary

> *Partly done in Revision 8*: `.github/workflows/tauri-build.yml` already runs steps 1–3 inline (PyInstaller → `rustc -vV` triple → copy into `binaries/`), and `.gitignore` covers the copied binary. The Windows build of the sidecar and `tauri build --no-bundle` were verified locally. Still to do: the script (so CI and developers share it), the spec's data files, and the runtime smoke test.

New `amp/scripts/build_sidecar.py`:

1. Run `pyinstaller amp-backend.spec --noconfirm`.
2. Get the target triple from `rustc -vV` (the `host:` line).
3. Copy `dist/amp-backend[.exe]` to `frontend/src-tauri/binaries/amp-backend-<triple>[.exe]`.

- `amp-backend.spec`: add hidden imports and data for `yt_dlp` (extractors are imported lazily), `yt_dlp_ejs` package data, and `ytmusicapi` locales. Smoke test the built binary: `amp-backend --port 8123` → `/api/health` OK, and search works.
- Node.js is **not** bundled: document it as a prerequisite. The UI already reports `node_missing` (Phases 1 and 4).
- `.gitignore`: `frontend/src-tauri/binaries/`.

### 6.6 One developer launcher

- Keep `app.py` (the more complete one: logs, API tester, chunk viewer) and delete `amp_control.py`.
- Update `app.py`: read `backend.pid` and the port from the data dir. "Force kill" uses the PID file first and port scanning only as a fallback. Respect `AMP_PORT`.
- Update AGENTS.md and README: the Tauri app is the normal entry point, and `app.py` is a debugging tool.

### 6.7 Housekeeping

- `logger.py`: `RotatingFileHandler(maxBytes=5 MB, backupCount=3)` for `app.log` and `streaming.log`.
- `server.py`: replace `@app.on_event` with a `lifespan` context manager.
- Replace `datetime.utcnow()` with `datetime.now(timezone.utc)`. SQLite stores naive values, so either strip the tzinfo or set `DateTime(timezone=True)` consistently.
- ~~Icons: replace the placeholder~~ — done in Revision 8 (generated from `icon/logo-square.svg`).

### 6.8 Build & smoke test

- `npm run tauri build` produces an installer. Record the path in AGENTS.md. (Revision 8 removed the Tauri v1 `shell-sidecar` cargo feature that blocked compilation; only the installer bundle step is unverified locally.)
- Smoke checklist on a clean user profile (or after renaming the app data dir):
  1. App starts, sidebar shows "Backend: running" within 5 s.
  2. Search → play → audio within the TTFA target (Phase 4).
  3. Close the window → Task Manager shows no `amp-backend.exe` / `python.exe` left.
  4. Kill the app process from Task Manager → the backend exits within 2 s (parent watch).
  5. Relaunch → cached song replays from cache; data is in `%APPDATA%\com.amp.v2\`.
  6. Run two app instances → both work on different ports. (Or decide to enforce a single instance with `tauri-plugin-single-instance` and document it.)

---

## 4. Tests to add

| Test | Asserts |
|---|---|
| `test_main_data_dir_arg` | `main.parse_args(["--data-dir", tmp])` + configure → `settings.cache_dir` under tmp |
| `test_parent_watch_exits_on_eof` | spawn `python -m backend.main --parent-watch --port 0` with a stdin pipe, close stdin → process exits within 3 s |
| `test_pid_file_written` | startup writes `backend.pid` with the current PID |
| `test_rotating_handlers` | `configure_logging()` installs `RotatingFileHandler`s |
| Rust (optional) | `pick_free_port()` returns a bindable port |

---

## 5. Acceptance criteria

- [ ] Result of 6.0 recorded.
- [ ] `capabilities/default.json` contains no `shell:*` permissions.
- [ ] Smoke checklist 6.8 passes on Windows (all 6 items).
- [ ] `grep -rn "venv/Scripts/python.exe" frontend/src` returns nothing.
- [ ] `amp_control.py` deleted; README and AGENTS.md describe the new startup model.
- [ ] Known Issues in AGENTS.md updated: "PyInstaller binary not built" and "Tauri app not built" closed or replaced with what's still left.

## 6. Risks and notes

- **Free ports break bookmarked dev URLs** (`http://127.0.0.1:8000/docs`). Mitigation: `AMP_PORT=8000` in dev, set by `npm run tauri dev` through `.env` or the launcher.
- **PyInstaller and yt-dlp**: yt-dlp updates mean rebuilding the sidecar. Note this in README, and consider a later "yt-dlp outdated" warning in health (compare the version against PyPI at most once a day). Out of scope here.
- **Antivirus false positives** on PyInstaller one-file binaries are common on Windows. If it happens, switch the spec to one-folder mode (Tauri sidecars can be a directory plus `resources`).
