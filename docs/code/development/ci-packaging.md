# CI & packaging

## GitHub Actions

Both workflows run on every push and pull request, on `ubuntu-latest`.

=== "Python CI (`python-ci.yml`)"

    1. Python 3.13, `pip install -r amp/requirements.lock`
    2. `ruff check amp/backend/`
    3. `python -m pytest -m "not integration" --cov=backend --cov-report=xml` (from `amp/`)
    4. Upload `coverage.xml` to Codecov (needs the `CODECOV_TOKEN` secret; failures don't fail the job)

=== "Tauri Build (`tauri-build.yml`)"

    1. WebKitGTK and friends via apt, stable Rust, Rust cache
    2. Python 3.13 + `requirements.lock`, then `python scripts/build_sidecar.py --smoke`
    3. Node 24, `npm ci`, `npm test` (vitest)
    4. `npx tauri build --bundles deb`, the `.deb` uploaded as an artifact

Integration tests don't run in CI (they need YouTube). The smoke test's search does hit YouTube
from the runner, which can behave differently from a home connection.

## Lint

`.ruff.toml` at the repo root: pyflakes, pycodestyle errors, bugbear and bandit rules, tests
excluded. `fastapi.Depends/Query/Header` are declared immutable for B008. An inline `noqa` must
give its reason, e.g. `# noqa: S311 - backoff jitter, not crypto`.

## Coverage

Configured in `amp/pyproject.toml` (`[tool.coverage.*]`): source `backend`, tests omitted,
branch coverage. `fail_under = 60` is a regression floor; raise it as coverage grows.

## The sidecar

Release builds don't use Python from the system: the backend is frozen by PyInstaller into one
executable that Tauri bundles as a *sidecar*.

```bash
cd amp
python scripts/build_sidecar.py [--skip-pyinstaller] [--smoke]
```

1. `pyinstaller amp-backend.spec --noconfirm` → `dist/amp-backend[.exe]`
2. Reads the host target triple from `rustc -vV`.
3. Copies it to `frontend/src-tauri/binaries/amp-backend-<triple>[.exe]`, the name
   `bundle.externalBin` expects.
4. `--smoke`: starts the copy on a free port with a temporary data dir, checks `/api/health` and
   a search, closes its stdin and checks that it exits.

??? abstract "What `amp-backend.spec` takes care of"
    - `collect_submodules("backend")`: a hand-written list of hidden imports missed modules.
    - `collect_data_files("yt_dlp_ejs")` (the JS solver's scripts) and `ytmusicapi` locales.
    - `console=True`: the backend needs real stdin/stdout pipes for `--parent-watch` and log
      forwarding, and uvicorn's logging breaks on a `None` stdout. No window appears because
      Tauri spawns it with `CREATE_NO_WINDOW`.
    - One-file mode: data can't live next to `__file__` (a temporary extraction folder), hence
      the [frozen data dir default](../backend/lifecycle.md#data-directory).

Tauri checks that the sidecar file exists **even for `tauri dev`**, though the dev build runs
the venv. Rebuild it after any dependency change, yt-dlp especially, or the installed app keeps
the old copy.

Node.js isn't bundled: the installed app needs it on `PATH`.

## Installers

```bash
cd amp && python scripts/build_sidecar.py --smoke
cd frontend && npx tauri build
```

Outputs in `frontend/src-tauri/target/release/bundle/`: `msi/` and `nsis/` on Windows, `deb/` on
Linux. Installers aren't signed (SmartScreen warns), and antivirus tools may flag the one-file
sidecar; switching the spec to one-folder mode is the fix if that becomes a problem.

## Dependency upgrades

- **Python**: `requirements.txt` holds ranges (major versions capped, except yt-dlp).
  After upgrading, run the unit suite, then `pip freeze > requirements.lock`. CI installs from the lock.
- **yt-dlp**: `pip install -U "yt-dlp[default]"`, run the integration download test, refresh the
  lock, rebuild the sidecar. If extraction slows down or fails, re-measure the
  [player clients](../backend/extraction.md#player-clients).
- **Frontend**: `npm install`, `npm run build`, `npm test`; `package-lock.json` is committed.
- **Rust**: `Cargo.lock` is committed; `cargo update` then `npx tauri build`.

## Documentation

This site is built with MkDocs Material from `docs/` and `mkdocs.yml` at the repo root:

```bash
pip install -r docs/requirements.txt
mkdocs serve          # http://127.0.0.1:8000, live reload
mkdocs build --strict # fails on broken links
```

`mkdocs serve` uses port 8000 by default, like a manually started backend: pass
`-a 127.0.0.1:8001` if both run at once.
