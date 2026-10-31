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
| Refactor Phase 1 | Single-flight extraction ([plan](improvement-plan/phase-1-extraction.md)) | **DONE** — see Revision 9 |
| Refactor Phase 2 | Exact segment table from the fMP4 sidx ([plan](improvement-plan/phase-2-segment-table.md)) | **DONE** — see Revision 10 |
| Refactor Phase 3 | Download pipeline correctness ([plan](improvement-plan/phase-3-download-pipeline.md)) | **DONE** — see Revision 11 |
| Refactor Phase 4 | Playback UX & frontend ([plan](improvement-plan/phase-4-playback-ux.md)) | **DONE** — see Revision 12 |
| Refactor Phases 5–6 | Auth/security, lifecycle | Pending |

**Refactoring plan**: [improvement-plan/](improvement-plan/README.md) — phases 0–6. Phases 0–4 are done; Phases 5–6 are pending.

**Test results**: 325 unit tests pass (`pytest -m "not integration"`), 0 failed, 0 errors; backend coverage 86% (floor 60%). 10 frontend unit tests pass (`npm test`, vitest). All 14 integration tests pass (`test_integration.py` 8, `test_integration_download.py` 3 × 2 songs). Ruff clean. CI runs lint + unit tests on every push (Revision 8). Before Revision 7 the suite was actually at 18 failed / 54 errors under pydantic 2.14, despite the "147 pass" claims in earlier revisions.

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

### Revision 12 — Phase 4: playback UX & frontend (2026-10-31)

Plan: [improvement-plan/phase-4-playback-ux.md](improvement-plan/phase-4-playback-ux.md) · Branch: `fix/phase-4-playback-ux`

| # | Problem | Fix |
|---|---|---|
| F13 | `/ready` polled every 1 s (≤ 30×) before `audio.src`; the loop was never cancelled, so song A could take the element after song B | `POST /play` **resolves the stream** (blocks for the extraction), queues buffer-ahead, returns `{song_id, duration_ms, mime_type, segment_count, is_dash, epoch, cached_ahead}`. PlayerBar `load()`: generation counter + `AbortController` on `/play`; `audio.src` only if still the newest load. `/ready` and `api.isStreamReady` deleted |
| — | Same race on the backend: a slow `/play` for A finishing after `/play` B took the session back | `_play_seq`: only the newest `/play` starts the session and buffer-ahead; an overtaken one returns `message: "superseded"` |
| F17 | Invalid `song_id` → `ValueError` → 500 | `InvalidSongId(ValueError)` + handlers in `api/errors.py` (`ApiError`, `InvalidSongId`, `ExtractionError`) → `{"detail": {"code", "message"}}`. `invalid_id` 400, `unavailable`/`no_audio` 404, `auth_required` 401, `node_missing` 503, `extract_failed`/`segment_unavailable` 502. `/audio` and `/stream/info` use the same shape (was `{detail, code}` / plain 404) |
| — | "Audio error (code 4)" for every failure | `fetchApi` parses the code into `ApiError.code`; `player/errors.ts` `describeError` / `describeMediaError` → e.g. "Sign in required for this track", "Node.js not found. Install it and restart." |
| — | Queue/volume lost on restart (old "settings persistence: done" was false) | `state.ts` saves `{songs, currentIndex, volume}` to `localStorage` `amp.queue.v1` (debounced 500 ms, try/catch); restored **paused**, play button runs `load()`. `player/persistence.ts` validates what it reads (11-char IDs, clamped index/volume) |
| — | Next song only extracted after `ended` | `< 20 s` left or `> 80 %` → `POST /buffer/{next}?mode=prefetch` once per song: resolves stream info, queues init + 2 segments at **LOW**, session untouched (`StreamingService.prefetch`) |
| 3.x | Mid-stream abort (Phase 3) left to the player | One reload per load on `MEDIA_ERR_NETWORK`, resuming at `currentTime` |
| 4.7 | — | `SegmentBar.tsx` (unused) deleted; segment offsets in a `useMemo` (was O(n²) per render); `duration_ms` from `/play` shown until `loadedmetadata`; spinner on the play button while loading |

**TTFA (G1)**, measured in headless Edge (Chromium, same engine as WebView2) on the real frontend (Vite dev) against a scratch backend, from `load()` to the `playing` event, logged as `TTFA <id> <ms> cached=<bool>` to the API relay (Logs → "API relay"):

| Case | TTFA |
|---|---|
| Stream resolved + init/seg 0 on disk (`cached=true`) | **24 ms**, 26 ms (restored song, play clicked), 45 ms (next song after prefetch) |
| Uncached (`cached=false`): extraction (~1.1 s) + sidx head + seg 0 | 1,354 / 1,363 / 1,571 ms |
| Segments on disk but backend restarted (`cached=true`, stream info must be re-extracted) | 1,035 ms — the open "cached songs still need an extraction after restart" item |

Target met for the cached case (< 300 ms); uncached ≈ extraction + one segment.

**Verification** (same headless setup; page requests to `:8000` rewritten to the scratch backend over CDP — the user's own backend on :8000 was left running and untouched):
- 5 songs selected within ~2 s (4 uncached, last cached): relay shows **one** `src` line (`src Tmz3mpOq8aE (resolved in 1121 ms)`), the element plays it, backend session = `Tmz3mpOq8aE`.
- Unknown ID `aaaaaaaaaaa` → player shows "No audio stream for this track" (backend: 404 `no_audio`).
- Reload → queue (2 songs), index 1, volume 0.3 restored (`audio.volume` 0.3), no `src`, paused; clicking play → `src` + TTFA 26 ms.
- 2-song queue, seek to 12 s before the end: the next song was extracted + sidx-indexed at the seek (prefetch), its `/play` took 9 ms and TTFA 45 ms `cached=true`.
- HTTP: `/api/stream/bad/play` → 400 `invalid_id`; `/ready` → 404; prefetch → `queued: 2` (init already from the head fetch), session unchanged, init + seg 0–1 downloaded.
- Integration: 11/11 (`BAgTQhR8MLo`), 3/3 download (`Tmz3mpOq8aE`).
- `grep -rn "isStreamReady\|/ready" frontend/src backend` → nothing.

**Not verified:** the Tauri window itself (WebView2) — only Chromium headless; the network-error reload against a real mid-stream abort; the region-locked case (no region-locked ID at hand; the `unavailable` path is unit-tested).

**New tests:** `test_play_api.py` (24): `test_invalid_song_id_is_400`, invalid ID on 4 routes, every extraction code → status/code (+ unknown → `extract_failed`, failed `/play` doesn't take the session), `test_play_unavailable_is_404_coded`, table-build failure, `test_audio_error_is_json`, `/stream/info` coded, `test_ready_route_removed`, `test_play_returns_summary`, `cached_ahead`, `test_superseded_play_leaves_session_alone`, `test_prefetch_uses_low_priority`, prefetch then play re-ranks LOW → CRITICAL, prefetch error, bad mode 422, default mode. Frontend (new `vitest`, `npm test`, also in Tauri CI): `src/player/player.test.ts` (10: `describeError`, `describeMediaError`, persistence round-trip/junk/clamping, `shouldPrefetch`). `test_serving.py` assertions moved to the new body shape.

**Test results:** 325 unit tests pass, coverage 86% (`api/errors.py` 96%), ruff clean, 10 vitest tests, `npm run build` OK, 14/14 integration.

### Revision 11 — Phase 3: download pipeline correctness (2026-10-31)

Plan: [improvement-plan/phase-3-download-pipeline.md](improvement-plan/phase-3-download-pipeline.md) · Branch: `fix/phase-3-download-pipeline`

`services/streaming.py` is now a package (public imports unchanged, `from backend.services.streaming import …`):

| Module | Role |
|---|---|
| `service.py` | `StreamingService` facade + singleton (endpoint-facing methods keep their signatures) |
| `registry.py` | `SegmentRegistry`: `MISSING → QUEUED → IN_FLIGHT → DONE / ERROR`, one lock, per-key `Event`; `Priority`, `SegmentStatus` |
| `downloader.py` | `DownloadManager` (heap of hints, workers `claim()` before working) + `fetch_segment()` (P14 checks unchanged, unique tmp) |
| `cache.py` | `CacheStore`: paths, `layout.json`, per-file size map + running total, mtime LRU, reconciliation |
| `serving.py` | `serve_audio_range()`, `parse_range()`, `SegmentUnavailable` |
| `playback.py` | `PlaybackSession`, `buffer_plan()` |

| # | Problem | Fix |
|---|---------|-----|
| F6 | `_downloading` filled at enqueue: after a seek, `enqueue()` of a still-queued index returned False and the worker then dropped the stale item | Registry `request()`: QUEUED + newer epoch / better priority → re-rank and push a new heap item; workers skip items whose (priority, epoch) is no longer current. Heap order (priority, newer epoch, seq). Epoch = priority, not cancellation; in-flight downloads finish |
| F7 | `download_segment_sync` polled 30 s on queued work; `_iter_audio_range` skipped missing segments → body shorter than `Content-Length` (h11 error) | `ensure_segment()`: DONE → path; IN_FLIGHT → `Event.wait(SEGMENT_SYNC_TIMEOUT_S=15)`; else claim and fetch in the handler thread (jumps the queue). `/audio` ensures the first segment **before** headers (failure → JSON 502 `segment_unavailable`, or 404/401/502/503 from the extraction code); a later failure **raises** in the generator (connection aborted, never short). Evicted-before-open → one retry |
| F8 | Sync downloads not registered → worker + handler fetch the same segment, shared `NNNN.tmp`, Windows `PermissionError` | Only the claim holder downloads. `mkstemp(dir=song_dir, prefix="NNNN.", suffix=".tmp")` + fsync + `atomic_replace()` (retries `PermissionError`; identical-size winner → drop ours) |
| F11 | Eviction by download mtime (FIFO), full dir scan after every download, DB `last_accessed` never read | `touch()` bumps mtime when served (≤ once / 30 s) → real LRU. Running total from a size map; `maybe_evict()` O(1) under the limit. Protected: playing song's init + `index ≥ current − SEGMENT_BEHIND`, IN_FLIGHT, `layout.json`. `_touch_segment` DB writes removed |
| — | Status stayed DOWNLOADED after eviction; `/chunks` did `path.exists()` per segment every 500 ms | Eviction → `registry.evicted()` (MISSING). `/chunks` = `registry.snapshot()`, no filesystem calls; registry rebuilt by `reconcile()` at startup |
| 3.5 | Buffer-ahead on every 2 s position report | `update_position` re-requests only when the playhead enters a new segment. `start_playback` unqueues other songs' queued items (epochs are per-song, so they can't be ranked against each other); `stop_playback` unqueues the song (no epoch bump) |

**Also fixed on the way:** eviction must not delete a directory that only holds `layout.json` — the in-memory table still refers to it, and a manifest-less dir would be purged as legacy at the next start (caught by `test_manifest_not_counted_or_evicted`). `/audio` errors are JSON `{detail, code}` (the old empty-body 404 special case is gone; the `<audio>` element sees an error either way). New setting `SEGMENT_SYNC_TIMEOUT_S = 15`.

**Verification (live backend, scratch data dir, `CACHE_MAX_SIZE_MB=20`):**
- Seek check (`BAgTQhR8MLo`, uncached): play, then `seek` + 64 KB Range read at 0 % / 75 % / 10 % / 75 % / 10 % → 0.01 / 0.03 / 0.12 / 0.01 / 0.00 s. No `Too little data` (h11) in `app.log`. Via HTTP, not the Tauri UI.
- LRU check: full playback of songs 1–5, replay song 1 after 31 s (touch throttle), then songs 6–8 (8 songs, ~37 MB through a 20 MB cache, 3 eviction rounds). Song 1 — the **oldest download** — is still fully cached (27/27 files); songs 2–4 were evicted. Every full GET returned exactly `Content-Length` bytes while evicting. No ERROR lines.
- Integration: 11/11 (`BAgTQhR8MLo`), 3/3 download (`Tmz3mpOq8aE`), including `test_concat_equals_cdn_file`.
- `grep -rn "time.sleep(0.05)\|_downloading\|_seg_status" backend/services` → nothing.

**New tests:** `test_registry.py` (15), `test_downloader.py` (19: ordering incl. newer epoch, `test_seek_requeues_queued_segment`, `test_superseded_heap_item_skipped`, unqueued item skipped, handler error → ERROR, `fetch_segment` status classification / Content-Range / short read / `test_unique_tmp_names`), `test_cache.py` (12: `test_lru_respects_access`, touch throttle, `test_eviction_updates_registry`, protected + in-flight, manifest never evicted, `test_running_total_matches_scan`, reconcile rebuilds registry), `test_serving.py` (23: Range parsing, `test_range_first_segment_failure_returns_json_error`, `test_range_mid_stream_failure_raises`, vanished file refetch, extraction code → status, endpoint 502 / abort / 416), `test_playback.py` (7). `test_streaming.py`: `TestEnsureSegment` (`test_sync_and_worker_single_download`, `test_sync_claims_queued_item`, failure, timeout, vanished file, layout change mid-download, `/chunks` after eviction without FS calls), `TestBufferPolicy` (`test_position_update_noop_within_segment`, seek, cross-song unqueue, stop). Removed: old `TestDownloadManager` / `TestSegmentTask` / `TestPlaybackInfo` / `TestSegmentPaths` / `TestAtomicWrite` / `TestSegmentStatus` (moved or rewritten against the registry).

**Not verified:** the abort-mid-stream behaviour in the real webview (only via TestClient, which re-raises); Phase 4 handles retries in the player.

**Test results:** 301 unit tests pass, coverage 84% (registry/playback 100%, serving 94%, downloader 92%, cache 88%, service 81%), ruff clean, 14/14 integration.

### Revision 10 — Phase 2: exact segment table from the fMP4 sidx (2026-10-31)

Plan: [improvement-plan/phase-2-segment-table.md](improvement-plan/phase-2-segment-table.md) · Branch: `fix/phase-2-segment-table`

**Spike 2.0 — GO.** `scripts/dump_boxes.py` (kept as a dev tool) on itag 140, first 64 KB:

| Song | ftyp | moov | sidx | first moof | sidx refs |
|---|---|---|---|---|---|
| `BAgTQhR8MLo` (4,172,237 B) | 0 / 24 | 24 / 644 | 668 / 344 | 1012 | 26 × ~10 s |
| `Tmz3mpOq8aE` (3,797,479 B) | 0 / 24 | 24 / 735 | 759 / 320 | 1079 | 24 × ~10 s |

(offset / size in bytes.) The first 1,012 B of `BAgTQhR8MLo` (ftyp + moov + sidx, metadata only) are the fixture `backend/tests/fixtures/itag140_head.bin`.

| Area | Change |
|---|---|
| **2.1 `utils/mp4.py`** (new, pure) | `iter_boxes` (largesize, size 0), `parse_sidx` (v0/v1, rejects hierarchical), `parse_fmp4_index` → `Mp4Index(init_end, timescale, segments)`, `NeedMoreData(required_len)`. Durations rounded cumulatively so they sum exactly. `init_end` = first fragment − 1, so the virtual file **is** the CDN file (`total_bytes == filesize`) |
| **2.2 `_build_from_stream`** | m4a/mp4: `Range: bytes=0-65535` (reads at most that even if Range is ignored), parse sidx; on `NeedMoreData` re-fetch `required_len + 64 KB` (≤ 2 re-fetches, stops on a short read). Falls back to proportional on no sidx / HTTP error / sidx total ≠ extracted filesize; WARNING if durations differ from yt-dlp's by > 1 s. Head bytes stored as `init.bin` (no extra request on first play). `is_dash` kept for the API, now means "exact table" |
| **2.3 MPD removed** | `parse_mpd` and helpers deleted; `utils/dash.py` → `utils/layout.py` (`SegmentInfo`, `StreamInfo`, Range math), `test_dash.py` → `test_layout.py` (MPD tests dropped, layout/Range tests kept on a hand-built table). XML sniffing removed. Proportional builder renamed `_build_proportional_info` |
| **2.4 Cache identity** | `StreamInfo.itag` + `layout_id` = sha256(`itag|total_bytes|n_segments|method`)[:16]. `segments/{song_id}/layout.json` (atomic). Different `layout_id` → purge the song's dir, DB rows and in-memory statuses, log INFO, write the new manifest. `reconcile_cache()` deletes dirs without `layout.json` and rows whose `layout_id` ≠ the manifest's. LRU/cache-info ignore `layout.json` |
| **2.5 DB** | `Segment.layout_id` (String(16), nullable). `init_db()` drops + recreates `segments` if a column is missing (cache only) |
| **2.6 Spec** | DESIGN_DOC_2.md §6.1–6.4, §6.6, module tree, tests, glossary; READMEs |
| API | `/api/stream/info/{id}` adds `method`, `itag`, `layout_id` |

**Not done:** the optional 2.4 bonus (serve a cached song from `layout.json` without extracting after restart) — every first request after restart still extracts (~1 s with visionos). Workers already downloading under an old layout when a refresh changes it can still write one stale file after the purge (Phase 3 pipeline work).

**Verification:**
- Live backend on the Phase 1 scratch data dir (old `segments` table, pre-Phase-2 segments for `Tmz3mpOq8aE`): startup logged `segments table lacks ['layout_id']; recreating it` and `… 1 song dirs without layout.json removed`.
- `GET /api/stream/info/BAgTQhR8MLo`: `is_dash: true`, `method: sidx`, 26 segments (9,948 / 9,984 / 9,985 … ms), sum 257,613 ms (yt-dlp: 258 s), `total_bytes` 4,172,237, `init_range` [0, 1011].
- Seek to 50 % (`POST /api/stream/seek?position_ms=128806`) → `current_segment_index` 12 (segment 12 spans ~119.8–129.8 s); segments 12–15 downloaded. Via the API, not the Tauri UI.
- Integration `test_concat_equals_cdn_file`: sha256(init + segments) == sha256(one GET of the URL) for **both** pinned songs (26 and 24 segments). All 14 integration tests pass.
- `grep -rn parse_mpd backend` → nothing. `googlevideo` / `SAPISID=` in logs: 0.

**New tests:** `test_mp4.py` (18: boxes basic/largesize/size-0/offset/partial/invalid, sidx v0/v1/hierarchical/not-sidx/truncated, synthetic index, `first_offset`, cumulative rounding, `NeedMoreData`, no sidx before fragment, real fixture, virtual layout == file offsets). `test_layout.py` (layout_id stability/identity). `test_streaming.py`: `TestSidxTable` (exact table + init cached + manifest, 50 % maps to the right segment, big-moov re-fetch, short file doesn't loop, filesize mismatch / no sidx / HTTP 403 fall back), `TestLayoutIdentity` (layout change purges, same layout keeps cache, legacy dir deleted, foreign-layout rows dropped, manifest not counted/evicted), `TestSegmentsTableMigration`. Integration: `TestConcatEqualsCdnFile`.

**Action for users:** the first start after this revision deletes the whole segment cache (pre-Phase-2 dirs have no `layout.json`). Songs re-download on next play.

**Test results:** 228 unit tests pass, coverage 72% (`mp4.py` 84%, `layout.py` 96%), ruff clean, 14/14 integration.

### Revision 9 — Phase 1: single-flight stream extraction (2026-10-31)

Plan: [improvement-plan/phase-1-extraction.md](improvement-plan/phase-1-extraction.md) · Branch: `fix/phase-1-extraction`

New module **`backend/services/extractor.py`** (no FastAPI, no segments): `build_ydl_opts`, `select_audio_format` (pure), `ExtractedStream` / `ExtractionError`, `SingleFlight`, `BoundedDict` (moved here, re-exported by `streaming.py`), `StreamExtractor.get()` / `refresh(song_id, stale_url)`, `get_extraction_dependencies()`. `streaming.py` no longer imports yt-dlp (1,633 → 1,269 lines).

| # | Problem | Fix |
|---|---------|-----|
| F2 | Up to 24 extractions for a failing song (15 client × format strategies + retry without format) | One extraction per client in `YTDLP_PLAYER_CLIENTS`, `format="bestaudio/best"` + `ignore_no_formats_error`, format chosen in Python. "Video unavailable"/"Private video" stops the rotation; "Sign in to confirm"/age-gate tries the next client and is reported as `auth_required` |
| F4 | Duration always 180 s (DB never filled), size from a `clen=1` probe that appended a parameter, MIME hard-coded | `ExtractedStream` carries `duration_ms` (`info["duration"]`), `filesize` (`filesize` or URL `clen=`), `mime_type`, `title`, `expires_at` (URL `expire=` − 300 s). `_get_song_duration` / `_get_song_title` and the 180 s fallback removed; HEAD / `Range: 0-0` probe only when size is unknown |
| F5 | `/play`, `/chunks`, `/info`, `/audio` and 4 workers each built the stream; each 403'd worker re-extracted | `SingleFlight` around extraction **and** around stream-info building. 403 refresh passes the URL that failed: N workers → one re-extraction, late workers reuse the rebuilt table |
| — | `best`/`worst` could return muxed video (itag 18) | `select_audio_format` only returns audio-only formats (itag `STREAM_FORMAT` > m4a/mp4 by bitrate > any, e.g. 251). Muxed fallback is a commented-out hook |
| — | `_extract_failures` unbounded and unlocked | Negative cache is a `BoundedDict` of `(failed_at, ExtractionError)`: 5 min, 30 min for `unavailable`; `node_missing` not cached; `refresh()` clears it |
| 1.7 | — | `/api/health` → `services.extractor: {node, ejs, yt_dlp}` (computed once at startup). No `node` → `ExtractionError("node_missing")` without running yt-dlp |

**Client list — measured 2026-10-31, yt-dlp 2026.10.26, songs `BAgTQhR8MLo` / `Tmz3mpOq8aE`, signed out:**

| Client | Audio-only formats | itag 140 `available_at` delay | Extract time |
|---|---|---|---|
| `visionos` | 139, 140, 249, 250, 251 | none | ~1.0 s |
| `default` (tv_samsung + visionos + web) | 139, 140, 249–251 | ~5 s (URL is tv_samsung's) | ~1.8 s |
| `tv_samsung` | 140, 249–251 | ~5 s | ~1.6 s |
| `web`, `web_music`, `web_safari`, `tv`, `ios`, `mweb`, `android_vr` | none | — | — |

So **`YTDLP_PLAYER_CLIENTS = ["visionos", "default"]`**. This removes the ~5 s first-play wait (F20). `visionos` has `SUPPORTS_COOKIES=False`, and yt-dlp silently drops such clients when a cookie file is passed, so the extractor runs cookie-less clients **anonymously** and passes cookies only to clients that support them (`default`). Env override is JSON: `YTDLP_PLAYER_CLIENTS='["default"]'`. Re-measure after yt-dlp upgrades (extract with each client, list audio-only itags and `available_at`).

**Other changes:** `streaming.log` also receives `backend.services.extractor`; `amp-backend.spec` hidden import added; `refresh_stream_url(song_id, stale_url=None)` is a thin wrapper over `StreamExtractor.refresh`; `ExtractedStream` is never persisted (P24).

**Verification:**
- Live backend (scratch data dir), `/play` + 5× `/chunks` + 5× `/info` + `/audio` concurrently, then 6 more `/chunks` polls: **one** `Extracted stream` line (`client=visionos: itag=140 audio/mp4 mp4a.40.2, 3797479 bytes, 234.0s`); first 64 KB of audio in 1.3 s; `googlevideo` / `SAPISID=` in logs: 0. Not clicked through the Tauri UI.
- `GET /api/stream/info`: `Tmz3mpOq8aE` 234.0 s / 47 segments, `BAgTQhR8MLo` 258.0 s / 52 segments (both previously 37 from the fake 180 s); durations equal yt-dlp's.
- Integration: 10/10 (`test_integration.py` 8 + download 2) for `BAgTQhR8MLo`, 2/2 download for `Tmz3mpOq8aE`; stream info built in 1.2–1.3 s.

**Not verified:** the signed-in path with real cookies (anonymous `visionos` URL fetched with Cookie headers) — unit-tested with mocks only.

**New tests:** `test_extractor.py` (43): format selection (itag 140, rejects muxed 18/22, opus fallback, mp4-over-bitrate, empty/URL-less formats, `clen=`, `expire=`, metadata), error classification, `build_ydl_opts` (moved), `SingleFlight`, `StreamExtractor` (single-flight 10 threads → 1 extraction, error propagation, positive/expired/negative caches, 30 min `unavailable`, refresh dedup by stale URL, layout-change warning, rotation stop/next/no-audio/auth_required, `node_missing`, cookie file only for cookie clients and deleted), `available_at` (moved). `test_streaming.py`: `TestCdn403` rewritten + `test_concurrent_403s_rebuild_once`, `TestStreamInfo` (extracted duration → 49 × 5 s for 245 s, probe only without size, no 180 s fallback, stream-info single-flight, `ExtractionError` → `None`). `test_endpoints.py`: health reports extractor prerequisites. Removed: `TestTryExtract`, old `TestAvailableAt` / `TestBuildYdlOpts` in `test_streaming.py`.

**Test results:** 221 unit tests pass, coverage 69.9% (`extractor.py` 95%), ruff clean.

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
│   │   ├── extractor.py         # StreamExtractor (Revision 9)
│   │   └── streaming/           # package since Revision 11: service, registry, downloader, cache, serving, playback
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py            # Song, Playlist, PlaylistSong, LikedSong, Segment (SQLAlchemy 2.x)
│   │   └── session.py           # engine (WAL + busy_timeout=5000, P20), session_scope, get_db
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── logger.py            # app.log + streaming.log + in-memory ring buffer (1000 lines)
│   │   ├── mp4.py               # fMP4 box + sidx parser (pure, Revision 10)
│   │   └── layout.py            # SegmentInfo/StreamInfo + Range math (was dash.py; MPD parser removed in Revision 10)
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

**`utils/dash.py`** — Pure-function MPD parser *(historical: removed in Revision 10; replaced by `utils/mp4.py` (sidx) + `utils/layout.py`)*:
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
- yt-dlp extraction (P2): moved to `services/extractor.py` in Revision 9 — `js_runtimes=node`, Netscape cookie file (P23: 0600, deleted in finally)
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
│   │   ├── PlayerBar.tsx        # Play/pause/stop/next/prev, segment bar (click-to-seek, 500ms poll, P12), volume, load()
│   │   └── SongList.tsx         # Reusable song list with play-on-click
│   ├── player/                  # errors.ts, persistence.ts, prefetch.ts + player.test.ts (Revision 12)
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
- **Settings persistence**: Frontend-owned queue in `state.ts` via `useSyncExternalStore` *(correction: nothing was persisted until Revision 12)*

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
2. **Segment table**: exact, from the fMP4 `sidx` for itag 140 (init = ftyp+moov+sidx, virtual file == CDN file); proportional for WebM / no sidx. The MPD parser was removed (Revision 10)
3. **Cache identity**: `segments/{song_id}/layout.json` holds the `layout_id`; a different layout purges the song's cache; dirs without it are deleted at startup (Revision 10)
4. **Proportional fallback**: 5-second segments (SEGMENT_TARGET_SEC=5) from the extracted size + duration
5. **In-memory caches**: BoundedDict (insertion-order, max 256) instead of functools.lru_cache for mutability
6. **Tauri shell plugin**: Uses `@tauri-apps/plugin-shell` (v2) instead of deprecated `@tauri-apps/api/shell`; registered as `tauri-plugin-shell` in Cargo.toml
7. **Sidecar spawn**: `Command.create(venvPython(), ...)` in dev (uses venv), `Command.sidecar("amp-backend", ...)` in prod
8. **TestClient Host header**: Must set `Host: 127.0.0.1:8000` to pass middleware (P17)
9. **Windows file permissions**: `chmod 0600` not honored on Windows — tests relaxed with `platform.system()` check
10. **Open mode by default**: No token = no auth required. Token is opt-in for additional security.
11. **Settings paths**: tests redirect storage with `settings.configure_paths()` / `restore_paths()`, never by monkeypatching private attrs (Revision 7).
12. **yt-dlp client order**: `YTDLP_PLAYER_CLIENTS = ["visionos", "default"]` — visionos (no `available_at` delay, runs anonymously since it can't take cookies), then yt-dlp's default (~5 s `available_at` wait, uses cookies). One extraction per client (Revision 9).
13. **CI**: lint + unit tests run from the lock file; coverage config lives in `amp/pyproject.toml`; Tauri CI builds the PyInstaller sidecar before `tauri build` (Revision 8).
14. **Extraction is single-flight**: `StreamExtractor` (services/extractor.py) owns yt-dlp; `StreamingService` never imports it. Stream-info building is single-flight too; 403 refresh is keyed by the stale URL (Revision 9).
15. **Segment state**: only `SegmentRegistry` knows whether a segment is queued, in flight or on disk; request handlers use `ensure_segment()` and never poll; the cache LRU clock is file mtime (Revision 11)
16. **Play contract**: `/play` resolves the stream before returning, newest `/play` owns the session; the player sets `audio.src` only for its newest load. Streaming errors are `{detail: {code, message}}` (`api/errors.py`) (Revision 12)

## All 24 Pitfalls Addressed

| Pitfall | Implementation |
|---------|---------------|
| P1 — CDN requires Cookie | Cookie sent when authenticated; omitted when signed out (most URLs work without it) |
| P2 — yt-dlp needs JS runtime | Top-level `js_runtimes={"node": {}}` + `yt-dlp-ejs` solver (Revision 7; the earlier extractor_args form was ignored). `/api/health` reports node/ejs/yt-dlp; no node → `node_missing` (Revision 9) |
| P3 — Cache expensive lookups | `StreamExtractor`: single-flight + BoundedDict until URL `expire=`; negative cache 5/30 min (Revision 9) |
| P4 — Stream URLs expire | 403 → `refresh(song_id, stale_url)` + rebuild segment table, once per stale URL (Revision 9) |
| P5 — Content-Length strategies | Size from extraction (`filesize` / URL `clen=`); HEAD → Range 0-0 probe only if unknown (Revision 9) |
| P6 — Subprocess pipe deadlock | Separate stdout/stderr `.on("data")` handlers |
| P7 — Windows encoding | **Not currently handled in the frontend.** The `encoding: "utf-8"` spawn option was removed in Revision 2 (it caused a `transformCallback` error) and nothing replaced it |
| P9 — FastAPI route order | Specific routes before parameterized |
| P11 — localStorage relay | `POST /api/logs` → `GET /api/logs` |
| P12 — Overlapping polls | In-flight guard on health poll + SegmentBar poll |
| P13 — song_id validation | `^[A-Za-z0-9_-]{11}$` before file paths |
| P14 — Verify 206 + Content-Range | Check status, Content-Range match, byte count |
| P15 — Atomic writes | unique `mkstemp` tmp + fsync + `os.replace()` (Windows `PermissionError` retried) (Revision 11) |
| P16 — Real Range support | 200/206/416 with correct headers |
| P17 — Bind 127.0.0.1 + token + Host | Host always validated; token check only when configured |
| P18 — Seek epoch | Per-song counter; a seek's requests outrank older queued work, in-flight downloads finish (Revision 11) |
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
- [x] ~~First play of an uncached song waits ~5 s for `available_at`~~ — `visionos` first (Revision 9); the wait remains only when falling back to `default`
- [x] ~~DASH path never runs~~ — itag 140 gets an exact table from the fMP4 `sidx` (Revision 10); WebM stays proportional
- [ ] Cached songs still need an extraction after restart (Phase 2's optional `layout.json` bonus not done)
- [ ] Sidecar runtime not verified: PyInstaller binary builds, but launching it from the packaged app (data dir, `yt_dlp_ejs` data files, Node on PATH) is untested — Phase 6
- [ ] P7 (Windows encoding of sidecar output) not handled in the frontend
- [ ] `CODECOV_TOKEN` repository secret needed for the coverage badge
- [ ] MSE upgrade (§8.4) — optional, not done in Phase 4
- [ ] Phase 4 checked in headless Chromium only, not inside the Tauri/WebView2 window

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

# Frontend unit tests (vitest)
cd /e/Documents/TRAVAIL/packages/AMP2/amp/frontend && npm test

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
