# Testing

| Suite | Command (from) | Network | In CI |
|---|---|---|---|
| Backend unit (≈380 tests) | `python -m pytest -m "not integration"` (`amp/`) | no | yes |
| Backend coverage | add `--cov=backend --cov-report=term-missing` | no | yes, floor 60 % (currently ~87 %) |
| Backend integration | `python -m pytest -m integration` (`amp/`) | **yes** | no |
| Frontend unit | `npm test` (`amp/frontend/`) | no | yes (Tauri workflow) |
| Rust | `cargo test` (`amp/frontend/src-tauri/`) | no | no |
| Lint | `ruff check amp/backend/` (repo root) | no | yes |
| Type check + bundle | `npm run build` (`amp/frontend/`) | no | yes (via `tauri build`) |

## Backend unit tests

`amp/backend/tests/`, fully mocked (no network, no yt-dlp calls). One file per module:

| File | Covers |
|---|---|
| `test_config.py` | defaults, directory creation, `configure_paths` / restore, models CRUD |
| `test_mp4.py` | box iteration (largesize, size 0, truncation), `sidx` v0/v1/hierarchical, real header fixture |
| `test_layout.py` | virtual layout, Range → segment mapping, position → segment, `layout_id` |
| `test_extractor.py` | format selection, error classification, `build_ydl_opts`, `SingleFlight`, caches, client rotation, cookie handling |
| `test_registry.py` | the segment state machine |
| `test_downloader.py` | heap ordering, superseded items, `fetch_segment` checks, unique temp files |
| `test_cache.py` | LRU with `touch`, protection rules, accounting, reconciliation |
| `test_serving.py` | Range parsing, first-segment JSON errors, mid-stream abort, vanished files |
| `test_playback.py` | `buffer_plan`, session |
| `test_streaming.py` | `StreamingService`: sidx tables, layout identity, `ensure_segment`, 403 refresh, buffer policy |
| `test_play_api.py` | `/play` contract, error codes, superseded plays, prefetch |
| `test_endpoints.py` | middleware (Host, Origin, token), route order, auth and log routes |
| `test_auth.py` | SAPISIDHASH, credential store v2, v1 migration, cookie filtering, Netscape file |
| `test_lifecycle.py` | CLI args, data dir, PID file, socket bind, parent watch (incl. a real subprocess that must exit < 3 s after stdin EOF), log rotation |

### Fixtures (`conftest.py`)

| Fixture | Gives |
|---|---|
| `temp_dirs` | a temporary data dir + DB through `settings.configure_paths()`, restored afterwards |
| `reset_singletons` (autouse) | fresh service singletons for every test |
| `client`, `auth_headers` | `TestClient` of an app with a token, and its headers |
| `client_no_auth`, `no_auth_headers` | the same in open mode |

!!! warning "Test-writing rules"
    - Redirect storage with `temp_dirs`. Never `monkeypatch.setattr(settings, "_cache_dir", …)`:
      with pydantic 2.14 the undo deletes the attribute and breaks every later test.
    - `TestClient` requests need `Host: 127.0.0.1:8000`, or the middleware answers 403.
    - Don't make real network calls in unit tests: mock `requests` / yt-dlp.

`tests/fixtures/itag140_head.bin` is the first 1,012 bytes (ftyp + moov + sidx, no audio) of a
real itag 140 stream, used by the MP4 parser tests.

## Integration tests

Marked `@pytest.mark.integration`, deselected by default in CI. They hit YouTube for real, take a
couple of minutes, and work signed out.

| File | Does |
|---|---|
| `test_integration.py` | extraction, segment table, first segments, Range reads, seek, eviction and reconciliation on pinned songs (`dQw4w9WgXcQ`, `LTDxBgP0lqA`) |
| `test_integration_download.py` | downloads every segment of one song and checks that init + segments == one GET of the CDN file (sha256). Song: `BAgTQhR8MLo`, override with `AMP_TEST_SONG_ID` |

```bash
cd amp
python -m pytest backend/tests/test_integration_download.py -m integration -v -s
AMP_TEST_SONG_ID=Tmz3mpOq8aE python -m pytest backend/tests/test_integration_download.py -m integration -v -s
```

Run them after every yt-dlp upgrade. If a pinned song disappears or gets region-blocked, replace
its ID.

## Frontend tests

vitest, for the pure helpers that don't need a DOM:

- `src/player/player.test.ts`: `describeError`, `describeMediaError`, queue persistence
  (round trip, junk input, clamping), `shouldPrefetch`.
- `src/authSession.test.ts`: badge labels, a 401 from `/api/user/*` refreshes the status.

## Manual checks

The UI itself has no automated tests. When changing playback, check by hand in the app:
play an uncached song, seek into grey segments, skip quickly through several songs (only the last
should play), restart the app (queue restored, paused), and watch **Logs → API relay** for the
`TTFA` lines.
