# Install & launch

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

The first run compiles the Rust shell, which takes a few minutes. Then the AMP window opens and,
behind the scenes:

1. The app starts the backend on a free port, with its data in your per-user app data folder
   ([where?](configuration.md#where-amp-keeps-its-data)).
2. The sidebar shows **Backend: running** after a second or two.
3. When you close the window, the backend stops too. It also stops if the app crashes or is killed.

You can now [search and play](using-the-app.md). Signing in is [optional](sign-in.md).

!!! info "Only one AMP at a time"
    Starting AMP a second time brings the running window to the front instead of opening a
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
| Windows | `msi/AMP v2_2.0.0_x64_en-US.msi` and `nsis/AMP v2_2.0.0_x64-setup.exe` |
| Linux | `deb/…` (also built by CI on every push) |

The release app (`src-tauri/target/release/amp-v2[.exe]`) runs the bundled sidecar rather than
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
