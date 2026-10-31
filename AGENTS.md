# AMP v2 — Agent Progress Tracker

> **Project**: AMP v2 — YouTube Music DASH-segment streaming desktop app (Tauri + FastAPI)
> **Spec**: `DESIGN_DOC_2.md` (authoritative)
> **Last updated**: 2026-10-31

---

## Status Summary

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Backend core + auth | **DONE** |
| Phase 2 | DASH streaming core | **DONE** |
| Phase 3 | Tauri shell + player (frontend) | **DONE** |
| Phase 4 | Polish (Logs page, error surfacing, settings) | **DONE** |
| Phase 5 | Packaging + tests + README | **DONE** |
| Revision | Open mode (no token) + venv support | **DONE** |
| Refactor Phase 0 | Safety net + hotfixes ([plan](improvement-plan/phase-0-safety-net.md)) | **DONE** — see Revision 7 |
| Revision 8 | Logos, CI (lint + tests + coverage, Tauri build), badges, root README | **DONE** — see Revision 8 |
| Refactor Phases 1–6 | Extraction, segment table, pipeline, playback UX, auth/security, lifecycle | Pending |

**Refactoring plan**: [improvement-plan/](improvement-plan/README.md) — phases 0–6. Phase 0 is done; Phases 1–6 are pending.

**Test results**: 182 unit tests pass (`pytest -m "not integration"`), 0 failed, 0 errors; backend coverage 63% (floor 60%). All 12 integration tests pass (`test_integration.py` 8, `test_integration_download.py` 2 × 2 songs). Ruff clean. CI runs lint + unit tests on every push (Revision 8). Before Revision 7 the suite was actually at 18 failed / 54 errors under pydantic 2.14, despite the "147 pass" claims in earlier revisions.

**Auth model**: Open by default — no token required. Search, browse, and play work immediately. Cookie-based YouTube sign-in (optional) unlocks liked songs and user playlists.

**Virtualenv**: The app uses `amp/venv/` — the Tauri frontend spawns `venv/Scripts/python.exe` (Windows) or `venv/bin/python` (Unix).

### Revision 2 — Bug fixes + control panel + segment visualization (2026-10-27)

**User-reported issues fixed:**

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| Playback doesn't work | CSP missing `media-src` — `<audio>` blocked from loading `http://127.0.0.1:8000` | Added `media-src 'self' http://127.0.0.1:8000` to CSP in `index.html` and `tauri.conf.json` |
| No album art in search | CSP `img-src` missing `lh3.googleusercontent.com` (YouTube Music thumbnails) | Added `https://lh3.googleusercontent.com` to `img-src` |
| Cookie auth shows signed_in but likes/playlists fail | `YTMusic(auth=cookie_string)` — ytmusicapi expects headers dict, not raw Cookie string | Changed `get_client()` to pass `auth=self.get_auth_headers()` (dict with Cookie + Authorization + Origin) |
| `transformCallback` error on backend start | `encoding: "utf-8"` option in Tauri shell plugin spawn causes internal error | Removed `encoding` option from `Command.create()` and `Command.sidecar()` calls |
| Firefox browser import fails | No helpful error for locked profile; no cookie filtering | Added better error messages, YouTube-relevant cookie filtering, Firefox-specific hint |

**New features:**

| Feature | Files |
|---------|-------|
| **Tkinter control panel** | `amp/amp_control.py` — double-click GUI: start/stop/restart backend + frontend, force-kill port 8000/1420, health check, live log |
| **Segment visualization in player bar** | `PlayerBar.tsx` redesigned — seek bar is now segment-colored rectangles (green=downloaded, yellow=downloading+pulse, gray=pending, red=error), played portion overlaid, click-to-seek |
| **Cache info display** | New `GET /api/stream/cache-info` endpoint + `getCacheInfo()` in streaming service + cache bar in player (size, usage %, song/segment counts) |
| **Player bar height** | Increased from 80px to 96px to accommodate cache info row |

**New API endpoint:**
- `GET /api/stream/cache-info` — returns `{total_bytes, total_mb, max_mb, usage_pct, file_count, song_count, songs[]}`

### Revision 3 — yt-dlp format selector fix (2026-10-27)

**User-reported issue:** `ERROR: [youtube] Cjtt_BlQ6Us: Requested format is not available` — playback fails for videos without itag 140.

**Root cause:** Format selector `"140/bestaudio"` was too strict. When a video doesn't have itag 140 AND `bestaudio` also fails to match, yt-dlp returns an error instead of falling back.

**Fix in `backend/services/streaming.py`:**
- Changed format selector from `"140/bestaudio"` to `"140/bestaudio/best"` — always falls back to `best`
- Added `_try_extract()` helper with two-attempt strategy:
  1. Primary: `"140/bestaudio/best"` — prefers itag 140, falls back gracefully
  2. Fallback: `"best"` with `prefer_audio=True` — gets any format, then filters for audio-only in Python
- Audio format selection in Python: prefers itag 140 → MP4/M4A container → highest bitrate
- Added `nocheckcertificate` and `socket_timeout=15` for robustness
- Added negative cache (`_extract_failures` dict, 5-min TTL) — failed extractions are not retried for 5 minutes, preventing yt-dlp hammering
- Better error logging: logs available format IDs when no audio formats found
- Better 404 error message: "Stream not available - could not extract audio URL (video may be unavailable, region-locked, or format not found)"
- `refresh_stream_url()` now also clears the negative cache

**Frontend build**: `npm run build` succeeds — TypeScript compiles, Vite bundles 48 modules (191.68 kB JS, 7.95 kB CSS).

### Revision 4 — yt-dlp "page needs to be reloaded" fix (2026-10-29)

**User-reported issue:** `ERROR: [youtube] V_CqKqi1_Ec: The page needs to be reloaded` — repeated yt-dlp extraction failures, resulting in 404 on `/api/stream/{id}/audio`.

**Root cause:** yt-dlp's default web client on `music.youtube.com` triggers YouTube's stale-player-response detection ("The page needs to be reloaded"). The `music.youtube.com` subdomain is more aggressive about this check than `www.youtube.com`.

**Fix in `backend/services/streaming.py`:**

- **Changed watch URL** from `https://music.youtube.com/watch?v={id}` to `https://www.youtube.com/watch?v={id}`
- **Multi-strategy player client rotation** in `_extract_stream_url()` — tries 8 strategies in sequence:
  1. `player_client=android` + `po_token=android` + `bestaudio/best`
  2. `player_client=android` + `po_token=android` + `best`
  3. `player_client=web_safari` + `bestaudio/best`
  4. `player_client=web_safari` + `best`
  5. `player_client=tv_embedded` + `bestaudio/best`
  6. `player_client=tv_embedded` + `best`
  7. `player_client=mweb` + `bestaudio/best`
  8. `player_client=mweb` + `best`
- Each strategy builds its own `extractor_args` with `js_runtimes=node` + `player_client=...` + optional `po_token=...`
- First successful extraction wins; subsequent strategies are skipped
- Negative cache (5-min TTL) still applies after all 8 strategies fail

**Why this works:** The `android` player client uses a different API endpoint that doesn't trigger YouTube's web-client bot detection. `web_safari` and `tv_embedded` are additional fallbacks for videos where android is restricted.

> **Correction (Revision 7 / Phase 0):** client rotation was a no-op until Phase 0. The list-form `extractor_args` (`{"youtube": ["js_runtimes=node", "player_client=..."]}`) is silently ignored by yt-dlp, so `player_client`, `po_token` and `js_runtimes` never took effect. Every success was with yt-dlp's default client, and the explanation above was never actually tested.

**Test results:** 147 unit tests pass (`pytest -m "not integration"`). Frontend build succeeds.

### Revision 5 — yt-dlp format errors + integration download test (2026-10-29)

**User-reported issue:** `ERROR: [youtube] Tmz3mpOq8aE: Requested format is not available` — yt-dlp format selector fails even with `bestaudio/best` and `best` fallbacks.

**Root cause:** When yt-dlp's format selector matches nothing, it raises `DownloadError("Requested format is not available")` before returning the info dict. This means Python-side format filtering never runs. Some videos have formats that don't match `bestaudio` or `best` selectors (e.g., only video-only formats, or formats with unusual codec combinations).

**Fix in `backend/services/streaming.py`:**

- **Added `"worst"` format selector** as a third fallback per player client (12 strategies total: 4 clients x 3 format selectors)
- **Auto-retry without format selector** in `_try_extract()`: when `DownloadError` contains "not available", strips the `format` key from ydl_opts and retries. yt-dlp then uses its default behavior and returns all formats for Python-side filtering.
- **`_log_available_formats()` diagnostic**: when all 12 strategies fail, runs a final extraction with `listformats=True` and logs every available format (itag, ext, codecs, bitrate, URL presence). Helps identify region-locks, age-restrictions, or truly unavailable videos.
- `prefer_audio` now applies to both `"best"` and `"worst"` format selectors

> **Correction (Revision 7 / Phase 0):** client rotation was a no-op until Phase 0 (list-form `extractor_args`). The integration successes below all came from yt-dlp's default client.

**New integration test:** `backend/tests/test_integration_download.py` — **VERIFIED PASSING**

| Test | Song | Result |
|------|------|--------|
| `test_download_chunks` | `Tmz3mpOq8aE` (user's failing song) | PASSED — 37 segments, 3.62 MB, all verified, 0.5s |
| `test_download_chunks` | `BAgTQhR8MLo` (default) | PASSED — 37 segments, 4.17 MB, all verified |
| `test_download_chunks_quick` | Both songs | PASSED — init + 5 segments verified |

Run with:
```bash
cd /e/Documents/TRAVAIL/packages/AMP2/amp

# Default song (BAgTQhR8MLo) — both tests
venv/Scripts/python.exe -m pytest backend/tests/test_integration_download.py -m integration -v -s

# Your failing song
AMP_TEST_SONG_ID=Tmz3mpOq8aE venv/Scripts/python.exe -m pytest backend/tests/test_integration_download.py -m integration -v -s
```

**Bugs found & fixed during testing:**
- `temp_dirs` fixture sets `CACHE_MAX_SIZE_MB=1` (1 MB) — full song downloads (~4 MB) triggered LRU eviction mid-download, deleting earlier segments. Fixed by overriding `CACHE_MAX_SIZE_MB=10000` in the integration test fixture.
- `test_integration.py` had a `ScopeMismatch` bug — module-scoped `streaming_service` fixture using function-scoped `temp_dirs`. Changed to function scope in both integration test files.

**Test results:** 147 unit tests pass, 2 integration download tests **VERIFIED PASSING** (real network).

---


### Revision 6 — Runtime fixes (2026-10-30)

**Bug fixes:**

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| Vite command not found in frontend | PATH issue on Windows where `node_modules/.bin` isn't available to subprocess | Changed `vite` to `npx vite` in all npm scripts in `package.json` |
| Force kill says "nothing running" but port is in use | `is_port_open()` used socket-based check, `force_kill_port()` used netstat-based check - mismatch between methods | Enhanced `force_kill_port()` with multi-stage approach: 1) kill listening processes, 2) if port still open via socket test, find and kill any process using the port, 3) if still open, report as TIME_WAIT state |
| UnicodeDecodeError on French Windows | `text=True` uses cp1252 encoding which can't decode UTF-8 characters in netstat output | Replaced `text=True` with explicit `decode('utf-8', errors='ignore')` in all subprocess.run calls |

**Improvements to force kill:**
- Added `is_port_open()` (socket-based) for checking if port accepts connections
- Added `is_port_listening()` (netstat-based) for checking if there's a LISTENING process
- Added `find_any_pid_on_port()` to find any process using the port (not just listeners)
- Added `/T` flag to `taskkill` to kill child processes
- Check return codes from kill commands
- Better error messages for TIME_WAIT state

**Test results**: claimed 147 unit tests pass. In fact the suite was at 18 failed / 54 errors under pydantic 2.14 (see Revision 7).

### Revision 7 — Phase 0: safety net + hotfixes (2026-10-31)

Plan: [improvement-plan/phase-0-safety-net.md](improvement-plan/phase-0-safety-net.md) · Branch: `fix/phase-0-safety-net`

| # | Problem | Fix |
|---|---------|-----|
| F1 | Unit suite: 18 failed, 54 errors. `monkeypatch.setattr(settings, "_cache_dir", …)` on pydantic private attrs; with pydantic 2.14, `undo()` *deletes* them | `Settings.configure_paths(data_dir, db_file)` + `snapshot_paths()` / `restore_paths()` in `config.py`. `temp_dirs` fixture uses them; `test_auth.py` uses `temp_dirs`. No test patches private settings attrs any more |
| F2 | `extractor_args` was list-form, so yt-dlp ignored `player_client`, `po_token` and `js_runtimes` | `build_ydl_opts()` in `streaming.py`: top-level `js_runtimes={"node": {}}`, `extractor_args={"youtube": {"player_client": [...]}}`. Removed the fake `po_token=android` and `nocheckcertificate` |
| F3 | No JS challenge solver | `yt-dlp[default]` (pulls in `yt-dlp-ejs`). Startup logs whether `node` and `yt_dlp_ejs` are present (WARNING if missing) |
| F9 | CDN 403 called `mark_expired()`, so the URL refresh extracted *without* cookies | Removed `mark_expired()` / `reset_expired()` from the segment-403 path. Session expiry stays in `youtube.py` and `status(verify=True)` |
| F10 | Buffer-ahead window measured from song start (and O(n²)) | Duration accumulates from `start_index` (O(n)) |
| F12 | Browser import stored every site's cookies (`… or True`) and made a network request just to load them | `filter_youtube_cookies()` in `auth.py` (youtube.com + subdomains; `.youtube.com` wins over subdomains). `import_browser` and `SignInFlow` use `yt_dlp.cookies.extract_cookies_from_browser()` (no network) |
| F18 | AGENTS.md claims were inaccurate | Corrected test count, Revisions 4/5 notes, P2/P7 rows |

**Found during integration testing** (two behaviour changes caused by making the options actually work):

1. **`android` without a PO token returns only itag 18** (360p muxed video+audio, no itag 140). Once the shape was fixed, the app downloaded video, 7.3 MB instead of 4.2 MB. Following the plan's risk note, yt-dlp's default client (`None`) is now first in the strategy list. The diagnostic `_log_available_formats` also uses the default client.
2. **With node + ejs available, yt-dlp's default client becomes `TVHTML5`**, and its URLs return **403 for about 5 s** after extraction (yt-dlp's `available_at`; yt-dlp itself sleeps "as required by the site"). Before, no JS runtime was ever configured, so yt-dlp fell back to `VISIONOS`, which has no delay. Fix: `_try_extract` now selects a format via `_select_audio_format()` and then `_wait_until_available()` sleeps until `available_at` (capped at `MAX_AVAILABLE_AT_WAIT_S = 30`). **Cost: first play of an uncached song takes about 5 s longer.** Phase 1 (client strategy as a setting) should revisit this.
3. `test_integration_download.py` always asserted an `init.bin` file, which progressive streams never have (`has_init=False`). So it could not have passed for these songs, and the Revision 5 "VERIFIED PASSING" was not reproducible on the pre-Phase-0 code. The test now skips the init step when `has_init` is false.

**Dependencies:** `requirements.txt` / `pyproject.toml` cap major versions (yt-dlp deliberately uncapped, now `yt-dlp[default]>=2026.10.26`). New `amp/requirements.lock` (`pip freeze`). A fresh venv built from it passes the unit suite. README documents installing from the lock and the yt-dlp upgrade procedure.

**New tests:** `test_paths_survive_override_restore`, `test_temp_dirs_restores_paths` (config) · `TestBuildYdlOpts` (3), `TestCdn403::test_403_does_not_change_auth_state`, `TestBufferAhead` (2), `TestAvailableAt` (3) (streaming) · `TestFilterYoutubeCookies` (4) (auth) · `test_import_browser_keeps_only_youtube_cookies`, `test_import_browser_no_youtube_cookies` (endpoints).

**Test results:** 182 unit tests pass, 0 failed, 0 errors (also `test_auth.py` alone, and in reversed file order). Integration download tests **pass** for `BAgTQhR8MLo` (4,172,237 B) and `Tmz3mpOq8aE` (3,797,479 B), both itag 140 via the default client.

**Action for users:** anyone who used browser import before this revision has non-YouTube cookies stored in `ytm_session.json`. Log out and sign in again. Phase 5 migrates stored cookies.


### Revision 8 — Logos, CI, badges (2026-10-31)

Ported the useful pieces from the old `master` branch (a different, earlier layout: `app/` frontend, no DASH core) onto this codebase, then made the Tauri build actually work.

| Area | Change |
|------|--------|
| **Logos** | `icon/logo-square.svg` + `icon/logo-round.svg` (repo root, used by README). Favicon set + `site.webmanifest` in `amp/frontend/public/`, linked from `index.html` (same-origin, CSP unchanged). Copies are byte-identical to `master`. |
| **App icons** | Placeholder solid-colour icons replaced with a set generated from `logo-square.svg` (`npx tauri icon`): `32x32`, `128x128`, `128x128@2x`, `icon.png`, `icon.ico`, new `icon.icns` (added to `tauri.conf.json`). Unreferenced `256x256.png` / `512x512.png` placeholders removed. |
| **Root README** | New `README.md` with the logo, CI/Codecov/Tauri badges, quick start, quality checks, doc index. (The repo had no root README.) Codecov badge points at `master` (`develop` doesn't exist). |
| **Python CI** | `.github/workflows/python-ci.yml`: Python 3.13, `pip install -r amp/requirements.lock`, `ruff check amp/backend/`, `pytest -m "not integration" --cov`, Codecov upload (`CODECOV_TOKEN` secret, non-fatal). |
| **Tauri CI** | `.github/workflows/tauri-build.yml`: builds the PyInstaller sidecar first (copied to `binaries/amp-backend-<target-triple>`), then `npx tauri build --bundles deb`; uploads the `.deb` as an artifact. Node 24, `dtolnay/rust-toolchain` (master used the archived `actions-rs`), Rust cache. |
| **Ruff** | `.ruff.toml` from `master`, paths adapted; `fastapi.Depends/Query/Header` declared immutable (B008) instead of a blanket ignore. Fixed the 3 real findings: `l` → `row` (E741, `endpoints.py`), `noqa` with reason for backoff jitter (S311) and MPD parsing (S314). |
| **Coverage** | `[tool.coverage.*]` in `amp/pyproject.toml` (master's root `.coveragerc` would not be read with CI's `cd amp`). Tests omitted, branch coverage on. `fail_under = 60` as a regression floor (actual 63%; master's 80% would fail immediately). |
| **Deps** | `pytest-cov` and `ruff` added to dev deps; `requirements.lock` regenerated. |

**Found and fixed while verifying the Tauri build locally:**
- `Cargo.toml` requested `tauri` feature `shell-sidecar`, a **Tauri v1** feature that doesn't exist in v2, so the Rust shell had never compiled. Removed (sidecars come from `tauri-plugin-shell`). `npx tauri build --no-bundle` now succeeds (Windows, 2 min release build) with the PyInstaller sidecar present. `Cargo.lock` is now committed.
- `amp/.gitignore` had `src-tauri/target/`, anchored to `amp/`, so it never matched `amp/frontend/src-tauri/target/`. Fixed, and added `frontend/src-tauri/gen/schemas/`, PyInstaller `/build/`, the copied sidecar, and coverage/ruff outputs.
- `test_integration.py` had the same `init.bin` assumption as the download test (fails on progressive streams); fixed with the same `has_init` guard. It had never been run; all 8 tests now pass.

**Not ported from master:** `CONTRIBUTING.md` (describes the old layout and a `develop` branch that no longer exists), `.gitattributes`, `activate.*`, `run.sh`, the old `app/` frontend and its docs.

**Not verified:** the workflows themselves run only on GitHub; the Linux `.deb` bundle step and the Linux PyInstaller build were not run locally (the Windows equivalents were). The Codecov badge needs the `CODECOV_TOKEN` repository secret.

**Test results:** 182 unit tests pass, coverage 63.3%, ruff clean, frontend build OK, Tauri release build OK (Windows), 12/12 integration tests pass.

## Completed Work

### Phase 1 — Backend core + auth (DONE)

**Files created:**
```
amp/
├── backend/
│   ├── __init__.py
│   ├── main.py                  # entry: argparse --token + uvicorn
│   ├── config.py                # pydantic-settings singleton, creates .amp/ dirs on import
│   ├── api/
│   │   ├── __init__.py
│   │   ├── server.py            # FastAPI app, AuthMiddleware (Bearer + Host check P17), CORS, startup/shutdown
│   │   ├── endpoints.py         # library + streaming + logs routes (specific before parameterized, P9)
│   │   └── auth_routes.py       # 6 auth endpoints: status, cookies, cookie-header, import-browser, open-signin, logout
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth.py              # AuthService singleton, CredentialStore (atomic write, 0600), SAPISIDHASH, lazy YTMusic
│   │   ├── youtube.py           # YouTubeService singleton, ytmusicapi wrapper, SongData/PlaylistData dataclasses
│   │   └── streaming.py         # StreamingService + DownloadManager + PlaybackSession
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py            # Song, Playlist, PlaylistSong, LikedSong, Segment (SQLAlchemy 2.x)
│   │   └── session.py           # engine (WAL + busy_timeout=5000, P20), session_scope, get_db
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logger.py            # app.log + streaming.log + in-memory ring buffer (1000 lines)
│   │   └── dash.py              # MPD parser (pure functions, unit-testable)
│   └── tests/                   # 127 unit tests + integration tests
├── pyproject.toml
├── requirements.txt
├── amp-backend.spec             # PyInstaller spec for sidecar binary
├── .gitignore
└── README.md
```

**API routes (29 total, verified via OpenAPI schema):**
- `GET /`, `GET /api/health` (no auth)
- `GET /api/search`, `GET /api/song/{id}`, `GET /api/artist/{id}`, `GET /api/album/{id}`, `GET /api/playlist/{id}`
- `GET /api/user/playlists`, `GET /api/user/likes`
- `GET /api/stream/info/{id}`, `GET /api/stream/{id}/audio` (Range), `GET /api/stream/{id}/chunks`, `POST /api/stream/{id}/play`, `POST /api/stream/buffer/{id}`
- `POST /api/stream/pause`, `POST /api/stream/resume`, `POST /api/stream/stop`
- `POST /api/stream/position`, `POST /api/stream/seek`
- `GET /api/stream/playback-state`, `GET /api/stream/logs`
- `GET /api/auth/status`, `POST /api/auth/cookies`, `POST /api/auth/cookie-header`, `POST /api/auth/import-browser`, `POST /api/auth/open-signin`, `POST /api/auth/logout`
- `GET /api/logs`, `POST /api/logs`, `DELETE /api/logs`

### Phase 2 — DASH streaming core (DONE)

**`utils/dash.py`** — Pure-function MPD parser:
- SegmentList form (YouTube's audio manifests): `SegmentURL@mediaRange` → exact byte ranges
- SegmentTemplate + SegmentTimeline form: `S@t/d/r` entries → durations, `$Number$` token resolution
- Init segment: `SegmentList/Initialization@sourceURL` or `SegmentTemplate@initialization` + `@indexRange`
- Token resolution: `$RepresentationID$`, `$Bandwidth$`, `$Ext$`, `$Number$`
- `build_virtual_layout()` — maps virtual byte offsets to segment files
- `map_range_to_segments()` — maps HTTP Range header to segment file reads (spans boundaries)
- `position_ms_to_segment_index()` — exact mapping for seek
- `_parse_duration_to_ms()` — ISO 8601 duration parsing

**`services/streaming.py`** — StreamingService singleton:
- `DownloadManager`: PriorityQueue + ThreadPoolExecutor(4), daemon threads, start/stop lifecycle
- Segment download pipeline (P14): verify 206 + Content-Range match + byte count before writing
- Atomic writes (P15): tmp file + `os.replace()`
- Retry logic: 403 → refresh URL + rebuild segment table (P4), 429/5xx/timeout → backoff (0.5/1/2s + jitter), other 4xx → permanent ERROR
- LRU cache eviction: 500MB → 80%, protects current song's segments ahead of playhead
- Startup reconciliation: orphan files, missing files, size mismatches
- Real HTTP Range support (P16): 200 (full), 206 (partial), 416 (unsatisfiable)
- Epoch-based seek cancellation (P18): bump per-song epoch, stale workers discard results
- Buffer-ahead: CRITICAL (init + seg 0), HIGH (next 2), NORMAL (within 30s)
- Progressive fallback (P5): 3-strategy content-length probe (clen= param → HEAD → Range 0-0)
- yt-dlp extraction (P2): `js_runtimes=node`, Netscape cookie file (P23: 0600, deleted in finally)
- BoundedDict for in-memory caches (P19: max 256 entries)

**Pitfalls addressed:** P1–P5, P13–P24 (see design doc §10)

### Phase 3 — Tauri shell + player (DONE)

**Frontend files:**
```
amp/frontend/
├── package.json                 # React 18, react-router-dom 6, @tauri-apps/api 2, @tauri-apps/plugin-shell 2, Vite 5
├── vite.config.ts               # Port 1420, Tauri dev host support
├── tsconfig.json                # Strict TS, vite/client types
├── tsconfig.node.json
├── index.html                   # CSP meta (§8.5)
├── src/
│   ├── main.tsx                 # React entry with BrowserRouter
│   ├── App.tsx                  # Sidebar nav, backend status, sidecar lifecycle, PlayerBar
│   ├── api.ts                   # Typed fetch wrapper, all API methods, TypeScript types
│   ├── sidecar.ts               # BackendSidecar singleton: spawn dev/prod, health poll 1s (P12), stdout/stderr ring (P6/P7)
│   ├── state.ts                 # Frontend-owned queue + playback state (useSyncExternalStore)
│   ├── styles.css               # Dark theme, all components
│   ├── components/
│   │   ├── PlayerBar.tsx        # Play/pause/stop/next/prev, seek slider, volume, thumbnail, SegmentBar
│   │   ├── SegmentBar.tsx       # Segment status cells, click-to-seek, 500ms poll (P12 in-flight guard)
│   │   └── SongList.tsx         # Reusable song list with play-on-click
│   └── pages/
│       ├── Search.tsx           # Query box, results list, play per result
│       ├── Library.tsx          # Liked songs list
│       ├── Playlists.tsx        # User playlists + tracks
│       ├── Auth.tsx             # Import-from-browser, sign-in, status, logout
│       └── Logs.tsx             # Backend stdout, streaming logs, API log relay
└── src-tauri/
    ├── tauri.conf.json          # productName "AMP v2", CSP, externalBin: ["binaries/amp-backend"], icons
    ├── Cargo.toml               # tauri 2 + shell-sidecar feature + tauri-plugin-shell
    ├── build.rs
    ├── src/main.rs              # Registers tauri_plugin_shell
    ├── capabilities/default.json # shell:allow-spawn, shell:allow-stdin-write
    ├── icons/                   # generated from icon/logo-square.svg: icon.png, icon.ico, icon.icns, 32x32, 128x128, 128x128@2x
    └── binaries/                # gitignored; amp-backend-<target-triple> copied here from PyInstaller dist/ (CI does this)
```

**Build verified**: `npm run build` → TypeScript compiles clean, Vite bundles successfully.

### Phase 4 — Polish (DONE)

- **Logs page**: Backend stdout/stderr ring buffer, streaming logs, API log relay
- **Error surfacing**: Backend status indicator in sidebar (starting/running/stopped/error), manual restart button
- **Settings persistence**: Frontend-owned queue in `state.ts` via `useSyncExternalStore`

### Phase 5 — Packaging + tests + README (DONE)

- **PyInstaller spec**: `amp/amp-backend.spec` — bundles backend as `amp-backend` binary
- **Tauri icons**: Placeholder icons created (solid dark color, multiple sizes)
- **Tests**: 127 unit tests pass across 5 test files:
  - `test_dash.py` — 40+ tests: MPD parser (SegmentList, SegmentTemplate, error cases), virtual layout, range mapping, position-to-segment
  - `test_auth.py` — SAPISIDHASH, CredentialStore, AuthService, Netscape cookie file
  - `test_streaming.py` — song_id validation (P13), BoundedDict, SegmentTask priority, DownloadManager, PlaybackInfo, epoch, atomic write (P15), cache reconciliation, LRU eviction
  - `test_endpoints.py` — auth middleware (401/403), route ordering (P9), playback endpoints, log relay, auth endpoints
  - `test_config.py` — config defaults, dir creation, models CRUD
  - `test_integration.py` — marked `@pytest.mark.integration`, NOT RUN (requires network + cookies)
- **README.md**: Complete with architecture, quick start, configuration, API reference, testing, security

### Revision — Open mode + venv (2026-10-27)

**User request**: App must work out of the box without token/auth. Token and cookie auth should be optional features for user-specific data (likes, playlists), not required for search/streaming.

**Changes made:**

| File | Change |
|------|--------|
| `backend/config.py` | `AUTH_TOKEN` comment updated — optional, defaults to `None` |
| `backend/main.py` | `--token` CLI arg is now optional (removed `required=True`) |
| `backend/api/server.py` | AuthMiddleware: Bearer token check only enforced when token is configured. Host header validation always enforced (DNS-rebinding guard). Removed `RuntimeError` when no token. |
| `backend/services/auth.py` | `get_cdn_headers()` and `get_auth_headers()` no longer send empty Cookie header when signed out — omits Cookie entirely |
| `frontend/src/api.ts` | `fetchApi()` only attaches `Authorization` header when `authToken` is set. Added `clearAuthToken()` export. |
| `frontend/src/sidecar.ts` | Removed token generation. Dev spawn uses `venv/Scripts/python.exe` (venv python). No `--token` passed to backend. |
| `backend/tests/conftest.py` | Added `client_no_auth` fixture (app without token) and `no_auth_headers` fixture |
| `backend/tests/test_endpoints.py` | Added `TestOpenMode` class — 10 tests: health, search, streaming, auth status, user endpoints (401), log relay, Host validation, playback state, seek — all without token |
| `backend/tests/test_auth.py` | Added 2 tests: CDN/auth headers omit Cookie when signed out |
| `backend/tests/test_config.py` | Assert `AUTH_TOKEN is None` by default |
| `README.md` | Updated: open-by-default, optional auth, venv instructions, security section |

**Auth model:**
- **No token configured** → API is open (Host header still validated)
- **Token configured** → All requests require `Authorization: Bearer <token>`
- **No YouTube cookies** → Search, browse, play work; `/api/user/likes` and `/api/user/playlists` return 401
- **YouTube cookies configured** → User-specific features work (via Auth page)

---

## Architecture Decisions Made

1. **Path format**: Files use `E:/Documents/...` (forward slashes) for `write_file` tool compatibility on Windows
2. **DASH parser**: Handles both SegmentList (YouTube's form) and SegmentTemplate+Timeline
3. **Segment durations**: When SegmentList@duration is present with timescale, use it; otherwise evenly divide total duration
4. **Progressive fallback**: 5-second segments (SEGMENT_TARGET_SEC=5) for faster first audio
5. **In-memory caches**: BoundedDict (insertion-order LRU, max 256) instead of functools.lru_cache for mutability
6. **Tauri shell plugin**: Uses `@tauri-apps/plugin-shell` (v2) instead of deprecated `@tauri-apps/api/shell`; registered as `tauri-plugin-shell` in Cargo.toml
7. **Sidecar spawn**: `Command.create(venvPython(), ...)` in dev (uses venv), `Command.sidecar("amp-backend", ...)` in prod
8. **TestClient Host header**: Must set `Host: 127.0.0.1:8000` to pass middleware (P17)
9. **Windows file permissions**: `chmod 0600` not honored on Windows — tests relaxed with `platform.system()` check
10. **Open mode by default**: No token = no auth required. Token is opt-in for additional security.
11. **Settings paths**: tests redirect storage with `settings.configure_paths()` / `restore_paths()`, never by monkeypatching private attrs (Revision 7).
12. **yt-dlp client order**: default client first; it needs `available_at` respected (~5 s on first play). Phase 1 makes the strategy list a setting (Revision 7).
13. **CI**: lint + unit tests run from the lock file; coverage config lives in `amp/pyproject.toml`; Tauri CI builds the PyInstaller sidecar before `tauri build` (Revision 8).

## All 24 Pitfalls Addressed

| Pitfall | Implementation |
|---------|---------------|
| P1 — CDN requires Cookie | Cookie sent when authenticated; omitted when signed out (most URLs work without it) |
| P2 — yt-dlp needs JS runtime | Top-level `js_runtimes={"node": {}}` + `yt-dlp-ejs` solver (Revision 7; the earlier extractor_args form was ignored) |
| P3 — Cache expensive lookups | BoundedDict with TTL for stream URLs and info |
| P4 — Stream URLs expire | 403 → refresh URL + rebuild segment table |
| P5 — Content-Length strategies | 3-strategy probe: clen= → HEAD → Range 0-0 |
| P6 — Subprocess pipe deadlock | Separate stdout/stderr `.on("data")` handlers |
| P7 — Windows encoding | **Not currently handled in the frontend.** The `encoding: "utf-8"` spawn option was removed in Revision 2 (it caused a `transformCallback` error) and nothing replaced it |
| P9 — FastAPI route order | Specific routes before parameterized |
| P11 — localStorage relay | `POST /api/logs` → `GET /api/logs` |
| P12 — Overlapping polls | In-flight guard on health poll + SegmentBar poll |
| P13 — song_id validation | `^[A-Za-z0-9_-]{11}$` before file paths |
| P14 — Verify 206 + Content-Range | Check status, Content-Range match, byte count |
| P15 — Atomic writes | tmp file + `os.replace()` |
| P16 — Real Range support | 200/206/416 with correct headers |
| P17 — Bind 127.0.0.1 + token + Host | Host always validated; token check only when configured |
| P18 — Seek epoch | Per-song monotonic counter, stale workers discard |
| P19 — Bound in-memory caches | BoundedDict max 256 entries |
| P20 — SQLite WAL + busy_timeout | WAL mode, busy_timeout=5000 |
| P21 — Blocking I/O in `def` | All blocking handlers are plain `def` |
| P22 — Webview codec support | Default itag 140 (AAC/MP4) |
| P23 — yt-dlp cookie temp file | Netscape file 0600, deleted in finally |
| P24 — Never log CDN URLs/Cookie | Sanitized logging |

## Known Issues / TODO

- [x] ~~Integration tests not run~~ — all 12 pass (Revision 8)
- [x] ~~PyInstaller binary not built~~ — builds locally (Windows) and in Tauri CI (Linux)
- [x] ~~Tauri app not built~~ — `shell-sidecar` (v1 feature) removed; release build succeeds (Revision 8). No installer bundle built locally yet
- [x] ~~Icon is a placeholder~~ — generated from the AMP logo (Revision 8)
- [ ] First play of an uncached song waits ~5 s for `available_at` (default yt-dlp client = TVHTML5) — Phase 1
- [ ] DASH path never runs: every stream is progressive, 37 × 5 s segments from a fake 180 s duration (F4) — Phases 1–2
- [ ] Sidecar runtime not verified: PyInstaller binary builds, but launching it from the packaged app (data dir, `yt_dlp_ejs` data files, Node on PATH) is untested — Phase 6
- [ ] P7 (Windows encoding of sidecar output) not handled in the frontend
- [ ] `CODECOV_TOKEN` repository secret needed for the coverage badge
- [ ] MSE upgrade (§8.4) — optional Phase-4 enhancement

## Environment Notes

- **OS**: Windows (paths use `E:/Documents/...`)
- **Python**: 3.13.7
- **Node.js**: v24.16.0, npm 11.15.0
- **Project root**: `E:/Documents/TRAVAIL/packages/AMP2/`
- **App root**: `E:/Documents/TRAVAIL/packages/AMP2/amp/`
- **Runtime data**: `amp/.amp/` (cache, logs — gitignored)
- **Database**: `amp/userdb.sqlite` (WAL mode)

## Verification Commands

```bash
# Unit tests (all pass)
cd /e/Documents/TRAVAIL/packages/AMP2/amp && python -m pytest backend/tests/ -m "not integration" -q

# Backend import check (open mode)
cd /e/Documents/TRAVAIL/packages/AMP2/amp && python -c "from backend.api.server import create_app; app = create_app(auth_token=None); print('OK')"

# Start backend (open mode — no token)
cd /e/Documents/TRAVAIL/packages/AMP2/amp && python -m backend.main --debug

# Start backend (with token)
cd /e/Documents/TRAVAIL/packages/AMP2/amp && python -m backend.main --token my-token --debug

# Using venv python directly
cd /e/Documents/TRAVAIL/packages/AMP2/amp && venv/Scripts/python.exe -m backend.main --debug

# Frontend build
cd /e/Documents/TRAVAIL/packages/AMP2/amp/frontend && npm run build

# Frontend dev server
cd /e/Documents/TRAVAIL/packages/AMP2/amp/frontend && npm run dev

# Tauri dev
cd /e/Documents/TRAVAIL/packages/AMP2/amp/frontend && npm run tauri dev

# Integration tests (requires network + cookies)
cd /e/Documents/TRAVAIL/packages/AMP2/amp && python -m pytest backend/tests/ -m integration

# Build PyInstaller sidecar
cd /e/Documents/TRAVAIL/packages/AMP2/amp && pyinstaller amp-backend.spec
# Then copy dist/amp-backend.exe to frontend/src-tauri/binaries/

# Lint (from repo root) — same as CI
amp/venv/Scripts/python.exe -m ruff check amp/backend/

# Unit tests + coverage (floor 60%) — same as CI
cd /e/Documents/TRAVAIL/packages/AMP2/amp && venv/Scripts/python.exe -m pytest -m "not integration" --cov=backend --cov-report=term-missing

# Install pinned deps / regenerate the lock after an upgrade
cd /e/Documents/TRAVAIL/packages/AMP2/amp && venv/Scripts/python.exe -m pip install -r requirements.lock
cd /e/Documents/TRAVAIL/packages/AMP2/amp && venv/Scripts/python.exe -m pip freeze > requirements.lock

# Local Tauri release build (sidecar first, like CI)
cd /e/Documents/TRAVAIL/packages/AMP2/amp && venv/Scripts/python.exe -m PyInstaller --noconfirm amp-backend.spec \
  && cp dist/amp-backend.exe "frontend/src-tauri/binaries/amp-backend-$(rustc -vV | sed -n 's/^host: //p').exe" \
  && cd frontend && npx tauri build --no-bundle

# Control panel (tkinter GUI — double-click or run)
cd /e/Documents/TRAVAIL/packages/AMP2/amp && python amp_control.py
```
