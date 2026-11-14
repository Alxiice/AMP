# Install & launch

## The quick way: download a release

Builds for Windows, macOS and Linux are on the
[Releases page](https://github.com/Alxiice/AMP/releases):

| System | Pick |
|---|---|
| Windows | `…-setup.exe` or `….msi` to install, or the `.zip` to run without installing |
| macOS | the `.dmg` (Apple Silicon) |
| Ubuntu / Debian | the `.deb` (`sudo apt install ./AMP_….deb`) |
| Other Linux | the `.AppImage` (`chmod +x`, then run it) |

You still need [Node.js](https://nodejs.org) 18+ on your `PATH` (see below). The builds aren't
signed: on Windows, SmartScreen warns on first launch ("More info" → "Run anyway"); on macOS,
right-click the app and choose Open the first time.

The rest of this page is for running AMP from the source code.


## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | 3.10+ (3.13 used in CI) | runs the backend |
| Node.js | 18+ (24 used in CI) | builds the frontend, and **yt-dlp needs it at runtime** to solve YouTube's JavaScript challenges |
| Rust toolchain | stable | builds the Tauri desktop shell ([rustup.rs](https://rustup.rs)) |

Node.js must be on `PATH` whenever AMP runs, including the installed app: it is not bundled.

??? note "Extra system packages on Linux"
    Tauri needs WebKitGTK and a few libraries. On Debian/Ubuntu (the list CI uses):

    ```bash
    sudo apt-get install -y libwebkit2gtk-4.1-dev libgtk-3-dev \
      libayatana-appindicator3-dev librsvg2-dev libxdo-dev libssl-dev pkg-config
    ```

## 1. Set up the backend

All commands run from the `amp/` folder of the repository.

=== "Windows"

    ```powershell
    cd amp
    python -m venv venv
    venv\Scripts\activate
    pip install -r requirements.lock
    ```

=== "Linux / macOS"

    ```bash
    cd amp
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.lock
    ```

`requirements.lock` pins exact versions that pass the test suite. `requirements.txt` holds the
looser version ranges it was generated from.

!!! tip "The venv location matters"
    In development, the desktop app runs the backend with `amp/venv`'s Python. If your
    interpreter lives elsewhere, point the `AMP_PYTHON` environment variable at it.

## 2. Build the sidecar (once)

```bash
python scripts/build_sidecar.py
```

This builds the backend into a single executable with PyInstaller and copies it to
`frontend/src-tauri/binaries/amp-backend-<target-triple>[.exe]`. Release builds ship this file.
Tauri refuses to start without it, **even in development**, where the venv is used instead.

Rebuild it after every dependency upgrade (yt-dlp especially). Add `--smoke` to also start the
binary and check that it answers, searches and exits cleanly.

## 3. Run the desktop app

```bash
cd frontend
npm install
npm run tauri dev
```

On Windows, double-clicking `AMP.bat` at the repository root does the same (it runs `npm install`
first if `node_modules` is missing). The sidecar from step 2 is still needed.

The f## 4. Build the app (optional)

One script builds everything and puts the results in `build/` at the repository root:

```bash
cd amp
python scripts/build_release.py              # executable + installers for this system
python scripts/build_release.py --exe-only   # executable only
```

| In `build/` | What |
|---|---|
| `AMP-1.0.0-<os>-<arch>/` | `AMP[.exe]` with `amp-backend[.exe]` next to it. Run `AMP` directly, nothing to install; keep both files together. |
| `AMP-1.0.0-<os>-<arch>.zip` / `.tar.gz` | the same folder, archived |
| `installers/` | Windows: `.msi` and `-setup.exe` · macOS: `.dmg` · Linux: `.deb` and `.AppImage` |

Options: `--bundles deb,appimage` (or `msi`, `nsis`, `dmg`…) picks installer types, `--smoke`
tests the backend executable before packaging, `--skip-sidecar` reuses the one already built.

A build runs the bundled backend, not your venv, so it works without Python installed. Tauri
only builds for the system it runs on; the other systems are built by the
[Release workflow](../code/development/ci-packaging.md#releases).

e front instead of opening a
    second copy. Two backends sharing the same cache folder would delete each other's files.

## 4. Build an installer (optional)

```bash
cd amp
python scripts/build_sidecar.py --smoke
cd frontend
npx tauri build
```

The installers end up in `frontend/src-tauri/target/release/bundle/`:

| Platform | Output |
|---|---|
| Windows | `msi/AMP_1.0.0_x64_en-US.msi` and `nsis/AMP_1.0.0_x64-setup.exe` |
| Linux | `deb/…` (also built by CI on every push) |

The release app (`src-tauri/target/release/amp[.exe]`) runs the bundled sidecar rather than
your venv, so it works without Python installed.

!!! warning "Unsigned"
    The installers aren't code-signed: Windows SmartScreen will warn on first launch.

## Updating yt-dlp

When YouTube changes something, songs stop playing until yt-dlp catches up. yt-dlp is the one
dependency that isn't capped in `requirements.txt`, so you can upgrade it on its own:

```bash
cd amp
pip install -U "yt-dlp[default]"
python -m pytest backend/tests/test_integration_download.py -m integration -v -s
pip freeze > requirements.lock          # only if the test passed
python scripts/build_sidecar.py         # the sidecar bundles its own copy
```

The `[default]` extra installs `yt-dlp-ejs`, the JavaScript challenge solver that works with Node.js.
