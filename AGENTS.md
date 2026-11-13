# AMP — Agent Progress Tracker

> **Project**: AMP — YouTube Music DASH-segment streaming desktop app (Tauri + FastAPI)
> **Spec**: `DESIGN_DOC.md` (authoritative; `DESIGN_DOC_2.md` before Revision 20)
> **Docs**: `docs/` (MkDocs Material, `mkdocs.yml` at the root): usage guide + code reference. Update the matching page when behaviour changes; `mkdocs build --strict` must pass
> **Open work**: `TASKS.md` (requested features, proposals) and [Known Issues](#known-issues) below
> **Last updated**: 2026-11-13 (Revision 24)

This file was condensed in Revision 23. The full per-revision notes (measurements, verification
steps, new tests) are in git history: `git show 3ae702a:AGENTS.md`.

---

## Status Summary

| Phase | Description | Status |
|-------|-------------|--------|
| Phases 1–5 | Backend core + auth, DASH streaming core, Tauri shell + player, polish, packaging + tests | **DONE** |
| Revision | Open mode (no token) + venv support | **DONE** |
| Refactor Phases 0–6 | Safety net, single-flight extraction, sidx segment table, download pipeline, playback UX, auth & local API hardening, lifecycle & packaging | **DONE** — Revisions 7, 9–14 |
| Revisions 8, 15 | CI + logos; MkDocs documentation | **DONE** |
| Revisions 16–22 | Covers, queue, likes, redesign; OBS widget; launcher redesign; Developer page, settings, history; 1.0 naming + docs site; OS media controls; crossfade, normalization, now playing, albums | **DONE** |
| Revision 23 | Repo cleanup: dead code removed, markdown and docs brought up to date | **DONE** |
| Revision 24 | Release prep: `build_release.py` → root `build/`, Release workflow (Windows, macOS, Linux deb + AppImage), MIT license, docs copy rewrite | **DONE** |

Left from the refactoring plan: 5.6 (per-launch token), under Known Issues. The plan files
(`improvement-plan/`, `amp/AUTH_AUTO_EXTRACTION_DESIGN.md`) were removed in Revision 15 (last at `cc4453d`).

## Current model

- **Auth**: open by default — no token, but cross-site requests are refused (`Origin` /
  `Sec-Fetch-Site`, Revision 13). Search, browse and play work signed out. YouTube sign-in
  (Tauri webview; paste a Cookie header or Firefox import as fallbacks) unlocks likes and user
  playlists. Only youtube.com cookies are stored, with their domains (credential store v2).
- **Startup**: the Tauri app is the entry point. Rust (`src-tauri/src/backend.rs`) spawns the
  backend on a free port with `--data-dir <app data dir> --parent-watch` and stops it on exit; the
  frontend asks `backend_info` for the port. `amp/app.py` is a debugging launcher (backend on
  :8000 with `amp/.amp/`).
- **Python**: dev builds run `amp/venv/Scripts/python.exe` (Windows) / `amp/venv/bin/python`, or
  `AMP_PYTHON`. Release builds run the PyInstaller sidecar from `src-tauri/binaries/` — **rebuild it
  (`scripts/build_sidecar.py`) after any backend change**, the release app bundles whatever is there.

## Commit Guidelines

1. **Atomic commits**: each commit is a single logical change. Don't bundle unrelated changes.
2. **Clear scope**: self-contained and complete for its purpose; one feature across several files is fine.
3. **Messages**: `<type>: <description>`, type one of `feat`, `fix`, `docs`, `refactor`, `cleanup`, `test`, `chore`. Say what changed and why.
4. **No mega-commits**: split unrelated features, fixes and cleanup.
5. **Branches**: `feat/<name>`, `fix/<name>`, `docs/<name>`, `refactor/<name>`. Keep `master` clean.
6. **Docs**: when behaviour changes, update the matching page in `docs/` and check `mkdocs build --strict`.
7. **Tests**: in the same commit as the code they test.

## Revision log

Newest first. One entry per revision; details in git history.

| Rev | Date | Summary |
|---|---|---|
| 24 | 11-13 | **Release prep.** `amp/scripts/build_release.py`: sidecar + `tauri build` (`--exe-only` = `--no-bundle`, `--bundles`), copies the portable executable (`AMP` + `amp-backend`, archived) and installers into `<repo>/build/` (gitignored). `.github/workflows/release.yml`: on `v*` tags, Windows (msi, nsis), macOS arm64 (app, dmg), ubuntu-22.04 (deb, AppImage) → draft release with `CHANGELOG.md` as notes. `LICENSE` (MIT + no-affiliation/liability notice), `CHANGELOG.md`. Docs home copy rewritten in plain language, "Independent project" box replaced by a license note, hero screenshot no longer tilted (hover lift instead). README/install/CI docs updated |
| 23 | 11-13 | **Cleanup.** Removed dead code: DB models `Playlist` / `PlaylistSong` (never written; existing tables in old DBs are left alone), `AuthService.reset_expired` / `get_cookies_dict`, `StreamingService.refresh_stream_url`, `logger.clear_ring`; frontend `api.getSong` / `getArtist` / `getStreamInfo`, `getAuthToken` / `clearAuthToken`, `isTauriAvailable`. `DESIGN_DOC.md` (API, pages, player, CSP, DB), `TASKS.md` (done items removed), docs (layout, DB tables, tests, CI) and this file updated. 423 unit tests, ruff clean |
| 22 | 11-13 | **Crossfade, normalization, now playing, albums.** Two `<audio>` elements: in the last `fadeSec` s the next song takes the backend session and the old element fades out over its open `/audio` request (backend unchanged). Normalization from YouTube's `loudnessDb` (`GET /api/song/{id}/loudness`, ytmusicapi `get_song`), gain `min(1, 10^((−6 − dB)/20))`, target −6 dB; Web Audio rejected (needs CORS on `/audio`). `/now-playing` page, `/albums/:id` (`GET /api/album/{id}`, `GET /api/song/{id}/album`), queue ⋮ menu, default volume 0.5. Verified in the real Tauri window over CDP |
| 21 | 11-13 | **OS media controls** (Media Session API in `PlayerBar.tsx` → Windows SMTC / MPRIS / macOS). Fixed missing artwork: `googleusercontent.com` answers a `localhost` Referer with a 429 → `<meta name="referrer" content="no-referrer">` (pitfall P31). `AMP.bat` added |
| 20 | 11-07 | **1.0 naming**: "v2" dropped, identifier `com.amp.player` (old `com.amp.v2` data dir moved once by `backend.rs`), `DESIGN_DOC_2.md` → `DESIGN_DOC.md`. Docs site redesign (custom home, screenshots from `scripts/docs_screenshots.mjs`, glightbox), launcher page |
| 19 | 11-07 | **Developer page** (`/developer`), space bar play/pause, **Settings** (theme dark/light/system, accent, fade), **listening history** (table `listening_history`, `/api/history`, `player/history.ts`). `build.rs` fails clearly when the sidecar is missing |
| 18 | 11-07 | `app.py` launcher redesign (tkinter + stdlib only): sidebar pages, cards with live status, segment strip, log filters |
| 17 | 11-07 | **OBS widget**: `backend/widget.py` stdlib server on `WIDGET_PORT` (8001, `0` = off), `GET /`, `/now.json`, loopback only; `/play` takes optional `{title, artist, cover_url}` |
| 16 | 11-06 | Covers fixed (CSP `*.googleusercontent.com`, `Cover.tsx` fallbacks), playlist page, **play queue** (`player/queue.ts`, `QueuePanel`), **saved queues** (`/api/queues`), **likes** (`rate_song`), UI redesign (tokens in `styles.css`, `Icon`, `SongMenu`, toasts/dialogs). `dragDropEnabled: false` for HTML5 drag in WebView2 |
| 15 | 10-31 | MkDocs Material site (`docs/`), READMEs cut down, plan files removed |
| 14 | 10-31 | **Lifecycle & packaging** (refactor 6). The Tauri app had never started its own backend (`shell:allow-spawn` had no scope). Now Rust spawns/owns/stops it (`backend.rs`, job object), free port, `--data-dir`, `--parent-watch` (exits on stdin EOF), `backend.pid`, single instance, rotating logs, `build_sidecar.py --smoke`, `capabilities` = `core:default` only. MSI + NSIS built |
| 13 | 10-31 | **Auth & local API** (refactor 5): credential store v2 `(name, value, domain)`, v1 migration (allowlist), one primary sign-in (Tauri webview), Firefox-only import, cross-site `Origin` check in every mode, IPv6 Host parsing, sidebar session badge |
| 12 | 10-31 | **Playback UX** (refactor 4): `/play` resolves the stream and returns a summary; newest load/`/play` wins (`_play_seq`, generation counter); coded errors `{detail: {code, message}}`; queue/volume persisted; next-song prefetch; vitest. TTFA cached 24 ms, uncached ~1.4 s |
| 11 | 10-31 | **Download pipeline** (refactor 3): `streaming/` package, `SegmentRegistry` state machine, `ensure_segment()` (no polling, no short bodies), unique tmp files + `atomic_replace`, real LRU by mtime, O(1) eviction check |
| 10 | 10-31 | **Exact segment table from the fMP4 `sidx`** (refactor 2): `utils/mp4.py`, init = ftyp+moov+sidx so the virtual file is the CDN file; MPD parser removed; `layout_id` + `layout.json` cache identity |
| 9 | 10-31 | **Single-flight extraction** (refactor 1): `services/extractor.py`; one extraction per client, format chosen in Python (audio-only); real duration/size/MIME; clients `["visionos", "default"]` (no ~5 s `available_at` wait) |
| 8 | 10-31 | Logos and app icons, root README, CI (ruff, pytest + coverage, Tauri build), `Cargo.toml` fixed (v1-only `shell-sidecar` feature: the Rust shell had never compiled) |
| 7 | 10-31 | **Safety net** (refactor 0): unit suite actually green (pydantic private-attr monkeypatching broke 72 tests), `extractor_args` shape fixed (client rotation had been a no-op), `yt-dlp[default]` (EJS solver), cookie domain filtering, `requirements.lock` |
| 2–6 | 10-27 – 10-30 | Early fixes: CSP `media-src`/`img-src`, ytmusicapi auth headers, format selector fallbacks, `www.youtube.com` watch URL, Windows encoding/port-kill fixes in the launcher. Several claims of that period were later found wrong (client rotation never applied, test counts) — see Revision 7 |

## Architecture Decisions

1. **Segment table**: exact, from the fMP4 `sidx` for itag 140 (init = ftyp+moov+sidx, virtual file == CDN file); proportional 5 s segments for WebM / no sidx (Revision 10).
2. **Cache identity**: `segments/{song_id}/layout.json` holds the `layout_id`; a different layout purges the song's cache; dirs without it are deleted at startup (Revision 10).
3. **In-memory caches**: `BoundedDict` (insertion order, max 256) instead of `functools.lru_cache`, for mutability.
4. **Sidecar spawn**: from Rust only (`backend.rs`): debug → venv python, release → `sidecar("amp-backend")` via `tauri-plugin-shell` (Rust side; the webview has no `shell:*`). Free port, `--data-dir <app data dir>`, `--parent-watch` (Revision 14).
5. **TestClient Host header**: must be `127.0.0.1:8000` to pass the middleware (P17).
6. **Windows file permissions**: `chmod 0600` isn't honoured on Windows; tests check `platform.system()`.
7. **Open mode by default**: no token = no auth; a token is opt-in.
8. **Settings paths**: tests redirect storage with `settings.configure_paths()` / `restore_paths()`, never by monkeypatching private attrs (Revision 7).
9. **yt-dlp client order**: `YTDLP_PLAYER_CLIENTS = ["visionos", "default"]` — visionos (no `available_at` delay, runs anonymously since it can't take cookies), then yt-dlp's default (~5 s wait, uses cookies). Re-measure after yt-dlp upgrades (Revision 9).
10. **Extraction is single-flight**: `StreamExtractor` owns yt-dlp; `StreamingService` never imports it. Stream-info building is single-flight too; 403 refresh is keyed by the stale URL (Revision 9).
11. **Segment state**: only `SegmentRegistry` knows whether a segment is queued, in flight or on disk; handlers use `ensure_segment()` and never poll; the LRU clock is file mtime (Revision 11).
12. **Play contract**: `/play` resolves the stream before returning, the newest `/play` owns the session; the player sets `audio.src` only for its newest load. Streaming errors are `{detail: {code, message}}` (Revision 12).
13. **Auth**: one primary sign-in (Tauri webview → `/tauri-cookies`); store v2 keeps `(name, value, domain)`, youtube.com only. Cross-site requests refused by `Origin` / `Sec-Fetch-Site`; requests without `Origin` allowed for non-browser clients (Revision 13).
14. **Lifecycle**: the backend exits when its stdin closes, writes `<data>/backend.pid`, binds its own socket; the app is single-instance; logs rotate 5 MB × 3 (Revision 14).
15. **Frontend owns the queue**: `player/queue.ts` + `state.ts`; the backend only stores named copies (`/api/queues`) and history. Crossfade is frontend-only: the backend has one session, taken by the incoming song (Revisions 16, 22).
16. **CI**: lint + unit tests from the lock file; coverage config in `amp/pyproject.toml`; Tauri CI builds and smoke-tests the sidecar before `tauri build`; docs deploy to GitHub Pages from `master` (Revisions 8, 20).

## Pitfalls

The canonical list (P1–P31) is in `DESIGN_DOC.md` §10 and `docs/code/development/pitfalls.md`.
Most often relevant: P2 (yt-dlp needs Node + EJS, top-level `js_runtimes`), P12 (in-flight guard
on every poll), P13 (validate `song_id` before file paths), P14/P15 (verify 206 + Content-Range,
atomic writes), P17 (bind 127.0.0.1, validate Host), P24 (never log CDN URLs or cookies),
P25 (yt-dlp ignores malformed options silently), P27 (don't monkeypatch pydantic private attrs),
P31 (no Referer on cover images).

## Known Issues

**Open:**

- [ ] Cached songs still need an extraction after restart (~1 s) — TASKS P2
- [ ] First extraction in a freshly started sidecar takes ~3 s (frozen yt-dlp imports), later ones ~1.4 s — TASKS P4
- [ ] Per-launch API token (refactor 5.6) — `backend_info` already returns `token` (always `null`); needs a random token from Rust passed as `--token`, `setAuthToken` in the frontend, and `?t=<token>` accepted on `/audio` (`hmac.compare_digest`). Manual runs keep open mode — TASKS P9
- [ ] Installers unsigned (SmartScreen); antivirus false positives possible on the one-file sidecar — TASKS P10
- [ ] Search has no albums/artists/playlists results — TASKS P5
- [ ] Liked state of songs beyond the first 2000 likes is unknown (hearts show empty)
- [ ] Listened time of a crossfading song's last seconds isn't counted in the history
- [ ] `youtube_login.rs` user agent still says Chrome 125
- [ ] `CODECOV_TOKEN` repository secret needed for the coverage badge
- [ ] MSE upgrade (DESIGN_DOC §8.4) — optional

**Not verified by hand** (code paths and unit tests only):

- Installers installed and run; Linux/macOS lifecycle. The Release workflow (macOS dmg, AppImage, Windows on CI) hasn't run yet
- Webview sign-in with a real Google account → liked songs, liking a song, the user's own playlists list
- Release build since Revision 22 (rebuild the sidecar first: new routes)
- Crossfade: pause during the overlap; uncached next song (start delayed by `/play`, ~1.4 s)
- Media keys / Windows flyout buttons pressed by hand; the widget inside OBS
- Developer page "Restart backend", Logs page "Backend stdout" / Restart in the window; light theme by eye
- `app.py`: Frontend start (web/desktop), force kill, API Send button
- Data folder move from a real `com.amp.v2` folder (unit-tested on temp dirs)

## Environment Notes

- **OS**: Windows (paths `E:/Documents/...`)
- **Python**: 3.13.7 · **Node.js**: v24.16.0, npm 11.15.0 · **Rust**: 1.99.1, host `x86_64-pc-windows-gnu` (sidecar `amp-backend-x86_64-pc-windows-gnu.exe`)
- **Project root**: `E:/Documents/TRAVAIL/packages/AMP2/` · **App root**: `amp/`
- **Runtime data**: desktop app → `%APPDATA%\com.amp.player\` (cache, logs, `userdb.sqlite`, `backend.pid`); manual / `app.py` runs → `amp/.amp/` (gitignored) + `amp/userdb.sqlite` (WAL)

## Verification Commands

```bash
# Unit tests (from amp/)
cd /e/Documents/TRAVAIL/packages/AMP2/amp && venv/Scripts/python.exe -m pytest -m "not integration" -q

# Unit tests + coverage (floor 60%) — same as CI
cd /e/Documents/TRAVAIL/packages/AMP2/amp && venv/Scripts/python.exe -m pytest -m "not integration" --cov=backend --cov-report=term-missing

# Lint (from repo root) — same as CI
amp/venv/Scripts/python.exe -m ruff check amp/backend/

# Integration tests (network; cookies optional)
cd /e/Documents/TRAVAIL/packages/AMP2/amp && venv/Scripts/python.exe -m pytest -m integration
AMP_TEST_SONG_ID=Tmz3mpOq8aE venv/Scripts/python.exe -m pytest backend/tests/test_integration_download.py -m integration -v -s

# Backend alone (open mode, :8000, amp/.amp/)
cd /e/Documents/TRAVAIL/packages/AMP2/amp && venv/Scripts/python.exe -m backend.main --debug

# Frontend: build, unit tests (vitest), dev server, Tauri dev
cd /e/Documents/TRAVAIL/packages/AMP2/amp/frontend && npm run build
cd /e/Documents/TRAVAIL/packages/AMP2/amp/frontend && npm test
cd /e/Documents/TRAVAIL/packages/AMP2/amp/frontend && npm run dev
cd /e/Documents/TRAVAIL/packages/AMP2/amp/frontend && npm run tauri dev

# Sidecar (+ smoke: health, search, exit on stdin EOF), then installers
cd /e/Documents/TRAVAIL/packages/AMP2/amp && venv/Scripts/python.exe scripts/build_sidecar.py --smoke
cd /e/Documents/TRAVAIL/packages/AMP2/amp/frontend && npx tauri build   # → src-tauri/target/release/bundle/{msi,nsis}/

# Rust unit tests
cd /e/Documents/TRAVAIL/packages/AMP2/amp/frontend/src-tauri && cargo test

# Full build into <repo>/build/ (executable + installers; --exe-only for no installers)
cd /e/Documents/TRAVAIL/packages/AMP2/amp && venv/Scripts/python.exe scripts/build_release.py

# Docs
cd /e/Documents/TRAVAIL/packages/AMP2 && mkdocs build --strict

# Pinned deps: install / regenerate the lock after an upgrade
cd /e/Documents/TRAVAIL/packages/AMP2/amp && venv/Scripts/python.exe -m pip install -r requirements.lock
cd /e/Documents/TRAVAIL/packages/AMP2/amp && venv/Scripts/python.exe -m pip freeze > requirements.lock

# Debug launcher (tkinter)
cd /e/Documents/TRAVAIL/packages/AMP2/amp && venv/Scripts/python.exe app.py
```
