# AMP v2 — Improvement Plan

> **Source**: code review of `feature/auth-auto-cookie-extraction` @ `0397f83` (2026-10-30).
> **Spec**: `DESIGN_DOC_2.md` stays authoritative. Where a phase deliberately deviates from it, the phase says so and updates the spec.
> **Progress tracking**: `AGENTS.md`. Add a "Revision N" entry when each phase lands.
> **Status (2026-10-31)**: Phase 0 **done** (AGENTS.md Revision 7), plus logos/CI/badges and a working Tauri build (Revision 8). Phase 1 **done** (Revision 9), Phase 2 **done** (Revision 10), Phase 3 **done** (Revision 11). Next: Phase 4 (and Phase 5 can start in parallel).

This plan fixes the problems the review found, grouped into seven phases. Each phase has its own file: what it fixes, the tasks, the tests to add, and how to tell it is done.

## Phases

| Phase | File | Fixes | Effort | Depends on | Status |
|---|---|---|---|---|---|
| 0 | [phase-0-safety-net.md](phase-0-safety-net.md) | Red test suite, unpinned deps, ignored yt-dlp options, cookie leak, CDN-403 auth bug, buffer window | ½–1 day | — | **Done** (Rev. 7) |
| 1 | [phase-1-extraction.md](phase-1-extraction.md) | Redundant extraction strategies, thundering herd, missing metadata (duration/size/mime) | 1 day | 0 | **Done** (Rev. 9) |
| 2 | [phase-2-segment-table.md](phase-2-segment-table.md) | No real segment table (DASH path never runs), cache identity across formats | 1–2 days | 1 | **Done** (Rev. 10) |
| 3 | [phase-3-download-pipeline.md](phase-3-download-pipeline.md) | Seek drops queued work, truncated audio responses, tmp-file race, FIFO-not-LRU eviction | 1–2 days | 2 | **Done** (Rev. 11) |
| 4 | [phase-4-playback-ux.md](phase-4-playback-ux.md) | `/ready` polling, stale-load race, opaque errors, no persistence, no next-song prefetch | 1 day | 3 | Next |
| 5 | [phase-5-auth-security.md](phase-5-auth-security.md) | Four overlapping sign-in flows, stored foreign cookies, cross-site POSTs | 1 day | 0 (can run in parallel with 2–4) | Ready |
| 6 | [phase-6-lifecycle-packaging.md](phase-6-lifecycle-packaging.md) | Backend spawn/kill, orphan processes, data dir under PyInstaller, packaging, launchers | 1–2 days | 1, 4 | Pending (part done in Rev. 8) |

```
0 ──► 1 ──► 2 ──► 3 ──► 4 ──► 6
│                        ▲
└──► 5 ──────────────────┘ (5 can run alongside 2–4)
```

## Why this order

1. **Phase 0 comes first** because the unit tests are currently red: 18 failed and 54 errors. Without working tests, no later change can be checked. Phase 0 also ships five small hotfixes that fix real bugs with one-line changes.
2. **Extraction (1) comes before the segment table (2)**: the segment table needs the duration, file size and container that extraction currently throws away.
3. **The segment table (2) comes before the pipeline (3)**: the pipeline tests are written against the new segment layout, and the cache-identity work in Phase 2 changes how segments are keyed on disk.
4. **The pipeline (3) comes before UX (4)**: removing `/ready` polling is only safe once the audio endpoint guarantees it either returns the bytes or fails cleanly.
5. **Auth and security (5)** only touches `auth.py`, `auth_routes.py`, `signin_flow.py`, `server.py` and `Auth.tsx`, so it can run alongside 2–4.
6. **Lifecycle (6) comes last**: it changes how the app starts the backend and where data lives, and is easiest to verify once playback works end to end.

## Review findings by phase

| # | Finding | Evidence | Phase |
|---|---|---|---|
| F1 | Unit suite red (18 failed, 54 errors) | `monkeypatch.undo()` deletes pydantic private attrs on `settings` | 0 |
| F2 | `extractor_args` passed as a list, so yt-dlp ignores it; `js_runtimes` in the wrong place | `_configuration_arg("player_client")` returns `[]`. Verified. | 0, 1 |
| F3 | No JS challenge solver: default runtime is `deno`, `yt-dlp-ejs` is not installed, no `remote_components` | `YoutubeDL.py:544-555`, `find_spec('yt_dlp_ejs')` returns None | 0 |
| F4 | DASH path never runs; every song gets a 180 s duration, so always 37 segments | `streaming.log`: only "Progressive fallback … 37 segments" | 1, 2 |
| F5 | Stream info is built several times at once for the same song | Log: 3 builds in the same second | 1 |
| F6 | Re-queuing after a seek is deduplicated against stale queued tasks, then dropped | `streaming.py:225`, `:927` | 3 |
| F7 | Sync wait on a stale task leads to a short body vs `Content-Length` | `streaming.py:1126`, `:1481` | 3 |
| F8 | Fixed `NNNN.tmp` name; sync download not registered as in-flight, so two writers can race | `streaming.py:1103`, `:1134` | 3 |
| F9 | CDN 403 marks the user session expired, so the refresh extracts without cookies | `streaming.py:983` | 0 |
| F10 | Buffer window measured from song start instead of the playhead | `streaming.py:418` | 0 |
| F11 | Eviction is FIFO by mtime; full directory scan after every segment download | `streaming.py:1187-1259` | 3 |
| F12 | Browser import stores every site's cookies (the filter is `… or True`) | `auth_routes.py:98`, `signin_flow.py:178` | 0, 5 |
| F13 | `waitForReady` loop is never cancelled, so the wrong song can play; 1 s polling hurts G1 | `PlayerBar.tsx:106` | 4 |
| F14 | `shell:allow-spawn` has no scope; no kill on exit; Windows-only venv path | `capabilities/default.json`, `sidecar.ts:38` | 6 |
| F15 | Cross-site POSTs (no body or query params) are accepted in open mode | `server.py:43` | 5 |
| F16 | Under PyInstaller, `.amp/` and the DB resolve inside the temp extraction dir | `config.py:_project_root()` | 6 |
| F17 | `ValueError` from `validate_song_id` becomes a 500 | `endpoints.py` (no exception handler) | 4 |
| F18 | AGENTS.md claims tests are green and that the strategy rotation works | `AGENTS.md` | 0 |

Line numbers in the evidence column refer to `0397f83`. F1–F3, F9, F10, F18 are fixed (Phase 0); F2 (strategy explosion), F4 (metadata) and F5 (Phase 1); F4 (segment table, Phase 2); F6–F8 and F11 (Phase 3). F12 is fixed for new imports (stored cookies are migrated in Phase 5).

### Found during Phase 0 (not in the original review)

| # | Finding | Status |
|---|---|---|
| F19 | Without a PO token, `android` returns only muxed itag 18 (360p video) | Default client moved first (Phase 0); `YTDLP_PLAYER_CLIENTS` setting, android not in it (Phase 1) |
| F20 | With node + ejs, yt-dlp's default client (TVHTML5) gives URLs that 403 until `available_at` (~5 s) | Handled by waiting (Phase 0); Phase 1 puts `visionos` (no delay) first, so the wait only applies to the `default` fallback |
| F21 | Integration tests assumed an `init.bin` that progressive streams never have, so they could not pass | Fixed (Phase 0 / Rev. 8) |
| F22 | `Cargo.toml` requested Tauri v1 feature `shell-sidecar`; the Rust shell never compiled | Fixed (Rev. 8); `tauri build` works |

## Conventions for every phase

- **Branch**: one branch per phase, `fix/phase-N-<slug>`, created from `master` after the previous phase merges. Merge through a PR so CI runs.
- **Tests first where possible**: each phase lists the tests to add. Write the failing test, then the fix.
- **Done means all of these**:
  1. `venv/Scripts/python.exe -m pytest backend/tests -m "not integration" -q` passes with no failures or errors.
  2. `cd frontend && npm run build` succeeds (for phases that touch the frontend).
  3. CI is green on the branch: Python CI (`ruff check amp/backend/`, unit tests, coverage ≥ the `fail_under` floor in `amp/pyproject.toml`) and Tauri Build.
  4. The phase's acceptance criteria are checked, and any manual checks are written down in the AGENTS.md revision entry.
  5. `AGENTS.md` is updated with what changed and the real test count. `DESIGN_DOC_2.md` is updated wherever the phase changes the spec.
- **Don't widen scope**: anything you notice that a phase doesn't cover goes under "Known Issues / TODO" in AGENTS.md, not into the current branch.
- **Keep the pitfalls (P1–P28)** in DESIGN_DOC_2.md §10. If a change touches one, make sure it still holds.
