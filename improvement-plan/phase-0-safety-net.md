# Phase 0 — Safety net + hotfixes

**Goal**: get the unit tests passing again, pin the dependencies, and ship five one-line-scale fixes for bugs that are already hurting playback and privacy.

**Effort**: ½–1 day · **Depends on**: nothing · **Branch**: `fix/phase-0-safety-net`

---

## 1. Problems addressed

| # | Problem | Evidence |
|---|---|---|
| F1 | 18 failed, 54 errors in the unit suite | `pytest -m "not integration"` on venv with pydantic 2.14.1 |
| F2 | `extractor_args` and `js_runtimes` are silently ignored | Verified: list-form args make `_configuration_arg("player_client")` return `[]` |
| F3 | No JS challenge solver available to yt-dlp | default runtime is `deno`; `yt_dlp_ejs` not installed; no `remote_components` |
| F9 | CDN 403 marks the YouTube session expired, so the refresh extracts without cookies | `streaming.py:983` |
| F10 | Buffer-ahead window measured from song start, not playhead | `streaming.py:418` |
| F12 | Browser cookie import stores every site's cookies | `auth_routes.py:98` (`… or True`), `signin_flow.py:178` |
| F18 | AGENTS.md says 147 tests pass and that the client rotation works | `AGENTS.md` |

### Root cause of F1

`conftest.py` and `test_auth.py` do `monkeypatch.setattr(settings, "_cache_dir", …)`. These are pydantic **private attributes**, stored in `settings.__pydantic_private__`. With pydantic 2.14, `monkeypatch.undo()` *deletes* the attribute instead of restoring it. Reproduction:

```python
mp = pytest.MonkeyPatch(); mp.setattr(settings, "_cache_dir", "X"); mp.undo()
settings._cache_dir   # AttributeError — gone for every later test
```

The first test that patches settings passes. Every later test that touches settings then fails.

---

## 2. Tasks

### 0.1 Give `Settings` a public path API (fixes F1)

File: `amp/backend/config.py`

- Move the body of `model_post_init` into a public method:
  ```python
  def configure_paths(self, data_dir: Path | None = None, db_file: Path | None = None) -> None:
      """(Re)compute cache/segments/logs/db paths and create the directories."""
  ```
  - `data_dir` defaults to `_project_root() / AMP_DIR`, which is today's behaviour.
  - `db_file` defaults to today's `DB_PATH` resolution.
  - `model_post_init` just calls `self.configure_paths()`.
  - Phase 6 will reuse this method for `--data-dir`, so keep the signature as above.
- Add `snapshot_paths() -> dict` and `restore_paths(snapshot)` so tests can restore state without touching private attributes. Alternatively, `configure_paths` can return the previous values.

### 0.2 Fix the test fixtures (fixes F1)

Files: `amp/backend/tests/conftest.py`, `test_auth.py`, `test_streaming.py`, `test_endpoints.py`, `test_config.py`, `test_integration*.py`

- Replace every `monkeypatch.setattr(settings, "_…", …)` with one fixture:
  ```python
  @pytest.fixture()
  def temp_dirs(tmp_path):
      from backend.config import settings
      snap = settings.snapshot_paths()
      settings.configure_paths(data_dir=tmp_path / ".amp", db_file=tmp_path / "test.sqlite")
      ...reset DB engine, init_db()...
      yield {...}
      settings.restore_paths(snap)
      ...reset DB engine...
  ```
- Public fields such as `CACHE_MAX_SIZE_MB` can still be monkeypatched; those restore correctly.
- `grep -rn 'setattr(settings, "_' backend/tests` must return nothing.
- Add a regression test: run `temp_dirs` setup and teardown twice, then assert `settings.cache_dir` exists and points at the original location.

### 0.3 Pin dependencies

Files: `amp/requirements.txt`, new `amp/requirements.lock`, `amp/README.md`

- `requirements.txt`: add upper bounds on major versions (`pydantic>=2.5,<3`, `fastapi>=0.109,<1`, `sqlalchemy>=2,<3`, …). Leave **yt-dlp** without an upper bound, because it has to track YouTube changes, and change it to `yt-dlp[default]>=2026.10.26`, which pulls in `yt-dlp-ejs` (see 0.5).
- Once the suite is green, write `requirements.lock` with `venv/Scripts/python.exe -m pip freeze > requirements.lock`.
- README: install with `pip install -r requirements.lock`; upgrade yt-dlp with `pip install -U "yt-dlp[default]"` and then run the integration download test.

### 0.4 Hotfix: correct yt-dlp option shapes (fixes F2)

File: `amp/backend/services/streaming.py` (`_extract_stream_url`, `_log_available_formats`)

- Add a small pure helper. Phase 1 will move it into `extractor.py`.
  ```python
  def build_ydl_opts(player_client: str | None, fmt: str | None, cookie_file: str | None) -> dict:
      opts = {
          "quiet": True, "no_warnings": True, "skip_download": True,
          "socket_timeout": 15,
          "js_runtimes": {"node": {}},                     # top-level option, P2
      }
      if player_client:
          opts["extractor_args"] = {"youtube": {"player_client": [player_client]}}   # dict of lists
      if fmt:
          opts["format"] = fmt
      if cookie_file:
          opts["cookiefile"] = cookie_file
      return opts
  ```
- Remove `po_token=android`. It isn't a valid PO token; real tokens look like `<client>.<context>+<token>`.
- Remove `nocheckcertificate: True`. TLS verification should stay on.
- Keep the strategy loop for now, since Phase 1 replaces it. With the shape fixed, the loop will actually rotate clients for the first time, so watch the logs.

### 0.5 Hotfix: make the JS challenge solver available (fixes F3)

- Install `yt-dlp[default]` from 0.3, then check that `importlib.util.find_spec("yt_dlp_ejs")` is not `None`.
- If the package can't be installed, set `"remote_components": {"ejs:github"}` in `build_ydl_opts`. Prefer the package, so nothing is fetched at runtime.
- At backend startup, log whether `node` is on `PATH` (`shutil.which("node")`) and whether `yt_dlp_ejs` is importable. Log at WARNING if either is missing.

### 0.6 Hotfix: a CDN 403 is not an auth failure (fixes F9)

File: `amp/backend/services/streaming.py`

- In `_download_segment_with_retry`, remove `self._auth.mark_expired()` from the `_Auth403Error` branch.
- In `_rebuild_after_403`, remove `self._auth.reset_expired()`.
- Session expiry stays where it belongs: ytmusicapi 401/403 in `youtube.py`, and `status(verify=True)`.

### 0.7 Hotfix: buffer window relative to the playhead (fixes F10)

File: `amp/backend/services/streaming.py` (`_queue_buffer_ahead`)

- Accumulate duration starting at `start_index` instead of `sum(info.segments[:idx])`:
  ```python
  ahead_ms = 0
  for idx in range(start_index, len(info.segments)):
      offset = idx - start_index
      pri = CRITICAL if offset == 0 else HIGH if offset <= 2 else NORMAL
      if offset > 2 and ahead_ms > settings.SEGMENT_BUFFER_AHEAD_SEC * 1000:
          break
      self._dl_manager.enqueue(song_id, idx, pri, epoch)
      ahead_ms += info.segments[idx].duration_ms
  ```
- This also turns the loop from O(n²) into O(n).

### 0.8 Hotfix: only keep YouTube cookies (fixes F12)

Files: `amp/backend/api/auth_routes.py`, `amp/backend/services/signin_flow.py`, new helper in `amp/backend/services/auth.py`

- Add `filter_youtube_cookies(cookiejar) -> dict[str, str]`. It keeps a cookie only if `cookie.domain.lstrip(".")` is `youtube.com` or ends with `.youtube.com`. When the same name appears more than once, prefer `.youtube.com` over subdomains.
- Use it in `import_browser` (delete the `… or True` filter) and in `SignInFlow._get_cookies_from_browser`.
- Don't call `ydl.extract_info("https://music.youtube.com/")` just to load cookies. Use `yt_dlp.cookies.extract_cookies_from_browser(browser)`, which needs no network request.
- Phase 5 migrates cookies that are already stored. Until then, mention in the PR description that anyone who used browser import should log out and sign in again.

### 0.9 Correct AGENTS.md (fixes F18)

- Replace "147 unit tests pass" with the real count after this phase.
- Add a note to Revisions 4 and 5: "client rotation was a no-op until Phase 0 (list-form `extractor_args`); successes were with yt-dlp's default client".
- P7 row: the `encoding` spawn option was removed in Revision 2, so P7 is not currently handled in the frontend.
- Link this plan from the Status Summary.

---

## 3. Tests to add

| Test | File | Asserts |
|---|---|---|
| `test_paths_survive_override_restore` | `test_config.py` | override and restore twice; `settings.cache_dir` is still the original path |
| `test_ydl_opts_player_client_applied` | `test_streaming.py` | `YoutubeDL(build_ydl_opts("android", …)).get_info_extractor("Youtube")._configuration_arg("player_client") == ["android"]` (no network) |
| `test_ydl_opts_js_runtime_top_level` | `test_streaming.py` | `"js_runtimes"` is a top-level key and `"extractor_args"` is a dict |
| `test_403_does_not_change_auth_state` | `test_streaming.py` | mocked 403 on a segment, signed-in `AuthService` stays `SIGNED_IN` throughout, and the refresh gets a cookie file |
| `test_buffer_ahead_relative_to_playhead` | `test_streaming.py` | 60 × 5 s segments, `start_index=40`: queued indices are 40…46 (CRITICAL, 2 HIGH, NORMAL up to 30 s) |
| `test_filter_youtube_cookies` | `test_auth.py` | jar with `SID@.google.com`, `SID@.youtube.com`, `session@bank.example`: result is only `{"SID": <youtube value>}` |

---

## 4. Acceptance criteria

- [ ] `venv/Scripts/python.exe -m pytest backend/tests -m "not integration" -q` gives **0 failed, 0 errors**.
- [ ] `pytest backend/tests/test_auth.py -q` passes on its own as well (order independence).
- [ ] `grep -rn 'setattr(settings, "_' backend/tests` returns nothing.
- [ ] `requirements.lock` exists, and a fresh venv built from it passes the suite.
- [ ] Backend startup log shows `node` and `yt_dlp_ejs` both found.
- [ ] `test_integration_download.py` passes for `BAgTQhR8MLo` and `Tmz3mpOq8aE`.
- [ ] AGENTS.md has a "Revision 7 — Phase 0" entry with the real test count.

## 5. Risks and notes

- **Fixing the option shape changes behaviour.** Until now every extraction used yt-dlp's default client. Once `player_client=android` takes effect, results may change: some clients need PO tokens and return fewer formats. If the integration test regresses, put `None` (yt-dlp's default client) first in the strategy list. Phase 1 makes this list a setting.
- **The pydantic fix is a refactor of `config.py`**, which every module imports. Keep the existing properties (`cache_dir`, `segments_dir`, …) unchanged so no caller needs to change.
