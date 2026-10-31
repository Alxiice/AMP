<div align="center">
  <img src="./icon/logo-square.svg" width="200"/>
  <h1>
    AMP <br/>
  </h1>
  <i>Another Music Player : a local music player based on Youtube Music library.</i>
  <br/>
  <br/>
  <div>
    <a href="https://github.com/Alxiice/AMP/actions/workflows/python-ci.yml"><img src="https://github.com/Alxiice/AMP/actions/workflows/python-ci.yml/badge.svg" alt="Python CI" /></a>
    <a href="https://codecov.io/gh/Alxiice/AMP"><img src="https://img.shields.io/codecov/c/github/Alxiice/AMP/master?logo=codecov" alt="Code Coverage" /></a>
    <a href="https://github.com/Alxiice/AMP/actions/workflows/tauri-build.yml"><img src="https://github.com/Alxiice/AMP/actions/workflows/tauri-build.yml/badge.svg" alt="Tauri Build" /></a>
    <a href="https://Alxiice.github.io/AMP/"><img src="https://img.shields.io/badge/docs-GitHub_Pages-blue?logo=github" alt="Documentation" /></a>
  </div>
</div>

---

AMP is a desktop app that plays music from the YouTube Music library. Songs are downloaded in
small segments and cached on disk, so playback starts fast and you can seek right away. Search and
playback work without an account; signing in with YouTube adds your liked songs and playlists.

## Requirements

- **Python** 3.10 or newer
- **Node.js** 18 or newer, on your `PATH`. AMP needs it at runtime too, not just to build.
- **Rust** toolchain ([rustup.rs](https://rustup.rs))

## Launch the app

From the repository root:

```bash
cd amp
python -m venv venv
venv\Scripts\activate              # Linux/macOS: source venv/bin/activate
pip install -r requirements.lock
python scripts/build_sidecar.py    # first time only

cd frontend
npm install
npm run tauri dev
```

The AMP window opens. The first run takes a few minutes while Rust compiles. The app starts its
own backend and stops it when you close the window.

Later launches only need the last command:

```bash
cd amp/frontend
npm run tauri dev
```

## Build an installer

```bash
cd amp
python scripts/build_sidecar.py
cd frontend
npx tauri build
```

The installers are written to `amp/frontend/src-tauri/target/release/bundle/` (`.msi` and
`.exe` on Windows, `.deb` on Linux).

## Documentation

The full documentation (usage guide and code reference) is available on **GitHub Pages**:

📚 **[https://Alxiice.github.io/AMP/](https://Alxiice.github.io/AMP/)**

The docs are built with MkDocs from the `docs/` directory in this repository. To build and
preview them locally:

```bash
pip install -r docs/requirements.txt
mkdocs serve                       # then open http://127.0.0.1:8000
```

| | |
|---|---|
| [Install & launch](https://Alxiice.github.io/AMP/usage/install/) | prerequisites, setup, installers, updating yt-dlp |
| [Using the app](https://Alxiice.github.io/AMP/usage/using-the-app/) | search, player, queue, logs |
| [Troubleshooting](https://Alxiice.github.io/AMP/usage/troubleshooting/) | when a song won't play, the app won't start… |
| [Code](https://Alxiice.github.io/AMP/code/) | architecture, backend, frontend, tests, CI |

> **Personal prototype, not for distribution.** Fetching YouTube streams this way goes against
> YouTube's Terms of Service.
