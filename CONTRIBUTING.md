# Contributing to AMP

AMP is a desktop music player: a Tauri app (React frontend, Rust shell) that starts a local
FastAPI backend. The backend downloads YouTube Music audio in small segments with yt-dlp and
serves it to the player.

- **Design spec**: [`DESIGN_DOC.md`](DESIGN_DOC.md)
- **Open work and known issues**: [`TASKS.md`](TASKS.md)
- **Docs site** (usage guide + code reference): [`docs/`](docs/), built with MkDocs Material

## Getting set up

You need Python 3.13, Node.js 24 and Rust. yt-dlp also needs Node to solve YouTube's JavaScript
challenges.

```bash
cd amp
python -m venv venv
venv/Scripts/python.exe -m pip install -r requirements.lock   # venv/bin/python on Linux/macOS
cd frontend && npm install
```

Start the desktop app in dev mode with `npm run tauri dev` from `amp/frontend` (or `AMP.bat` on
Windows). The app starts its own backend on a free port and stops it on exit. To run the backend
on its own (port 8000, data in `amp/.amp/`):

```bash
cd amp && venv/Scripts/python.exe -m backend.main --debug
```

`amp/app.py` is a small debugging launcher that starts and watches the backend and frontend.

## Checks to run before a commit

```bash
# Backend: unit tests and lint (CI runs the same)
cd amp && venv/Scripts/python.exe -m pytest -m "not integration" -q
amp/venv/Scripts/python.exe -m ruff check amp/backend/

# Frontend: build and unit tests
cd amp/frontend && npm run build && npm test

# Rust
cd amp/frontend/src-tauri && cargo test

# Docs
mkdocs build --strict
```

Integration tests (`-m integration`) hit the network and are not run in CI.

Release builds bundle a PyInstaller copy of the backend. After any backend change, rebuild it
before building the app, otherwise the app ships the old backend:

```bash
cd amp && venv/Scripts/python.exe scripts/build_sidecar.py --smoke
cd amp && venv/Scripts/python.exe scripts/build_release.py   # executable + installers in build/
```

## Commits and branches

- One logical change per commit. Don't mix a feature, a fix and a cleanup.
- Write the message as one plain sentence that says what the commit does.
- Put tests in the same commit as the code they test.
- When behaviour changes, update the matching page in `docs/`.
- Work on a branch (`feat/…`, `fix/…`, `docs/…`, `refactor/…`) and keep `master` releasable.

## How the code is meant to work

A few rules that the code relies on. Breaking one usually breaks playback in a subtle way.

- **Segments**: the segment table comes from the audio file's own index (the fMP4 `sidx` box), so
  the file AMP serves is byte-for-byte the CDN file. Files without an index fall back to 5 s
  segments.
- **Cache**: each song's folder has a `layout.json`. If the layout changes, the song's cache is
  wiped. Folders without it are deleted at startup.
- **Extraction**: only `StreamExtractor` talks to yt-dlp, and each song is extracted once even if
  several requests ask for it at the same time.
- **Segment state**: only `SegmentRegistry` knows whether a segment is queued, downloading or on
  disk. Handlers call `ensure_segment()` and never poll.
- **Playback**: `/play` resolves the stream before it returns, and the newest `/play` wins.
  Errors are returned as `{detail: {code, message}}`.
- **Queue**: the frontend owns the play queue and crossfade. The backend only stores saved queues
  and the listening history.
- **Security**: the backend listens on 127.0.0.1 only, checks the Host header and refuses
  cross-site browser requests. Only youtube.com cookies are stored. Never log stream URLs or
  cookies.
- **Lifecycle**: the Rust shell starts the backend and owns it. The backend exits when its stdin
  closes.

## Common pitfalls

The full list is in `DESIGN_DOC.md` §10 and `docs/code/development/pitfalls.md`. The ones that
bite most often:

- yt-dlp needs Node and its EJS solver, and silently ignores options it doesn't understand.
- Validate `song_id` before building a file path from it.
- Check for a `206` and a matching `Content-Range` on every segment download, and write files
  atomically.
- In tests, redirect storage with `settings.configure_paths()`. Don't monkeypatch pydantic private
  attributes. The test client must send `Host: 127.0.0.1:8000`.
- Cover images must be loaded without a Referer, or Google's image servers answer with a 429.
- `chmod 0600` does nothing on Windows; tests check the platform.

## Code organization

<details>
<summary>Where things live (click to expand)</summary>

The full annotated tree is on the docs page [Repository layout](docs/code/layout.md).

```
(repo root)
├── DESIGN_DOC.md, TASKS.md      # design spec, open work and known issues
├── docs/, mkdocs.yml            # documentation site
├── .github/workflows/           # CI, docs deploy, release builds
└── amp/                         # the application
    ├── app.py                   # tkinter debug launcher
    ├── scripts/                 # build_sidecar.py, build_release.py, docs screenshots
    ├── backend/                 # Python (FastAPI)
    │   ├── main.py, lifecycle.py    # entry point, socket, pid file, parent watch
    │   ├── config.py                # settings and data paths
    │   ├── widget.py                # OBS now-playing widget
    │   ├── api/                     # routes, middleware, error model
    │   ├── services/
    │   │   ├── auth.py              # cookies and sign-in
    │   │   ├── youtube.py           # search, library, likes (ytmusicapi)
    │   │   ├── extractor.py         # stream extraction (yt-dlp)
    │   │   └── streaming/           # segment registry, downloader, cache, Range serving
    │   ├── database/                # SQLite models and session
    │   ├── utils/                   # MP4 index parser, byte-range math, logging
    │   └── tests/                   # pytest (unit + integration)
    └── frontend/
        ├── src/                     # React app
        │   ├── api.ts, sidecar.ts   # backend client
        │   ├── state.ts             # queue and playback store
        │   ├── player/              # pure helpers with vitest tests
        │   ├── components/          # PlayerBar, QueuePanel, song lists, menus
        │   └── pages/               # one file per page
        └── src-tauri/               # Rust shell
            └── src/                 # main.rs, backend.rs (starts/stops the backend),
                                     # youtube_login.rs (sign-in webview)
```

</details>
