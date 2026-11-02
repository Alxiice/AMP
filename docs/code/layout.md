# Repository layout

```
(repo root)
├── README.md                    # what AMP is + how to launch it
├── mkdocs.yml, docs/            # this documentation
├── AGENTS.md                    # progress tracker: revisions, decisions, known issues
├── DESIGN_DOC_2.md              # design spec, incl. the pitfall list P1–P30
├── icon/                        # logo-square.svg, logo-round.svg
├── .github/workflows/           # python-ci.yml, tauri-build.yml
├── .ruff.toml                   # lint rules
└── amp/                         # the application
    ├── backend/                 # Python package (FastAPI)
    ├── frontend/                # React app + src-tauri/ (Rust shell)
    ├── scripts/
    │   ├── build_sidecar.py     # PyInstaller → src-tauri/binaries/ (+ --smoke)
    │   └── dump_boxes.py        # dev tool: print the MP4 boxes of a stream's head
    ├── app.py                   # tkinter debug launcher
    ├── amp-backend.spec         # PyInstaller spec
    ├── pyproject.toml           # package metadata, pytest + coverage config
    ├── requirements.txt         # version ranges
    └── requirements.lock        # exact pins (CI, sidecar builds)
```

## Backend — `amp/backend/`

```
backend/
├── main.py                 # entry point: CLI args, socket, uvicorn
├── lifecycle.py            # socket bind, backend.pid, parent watch
├── config.py               # Settings (pydantic-settings), data paths
├── api/
│   ├── server.py           # create_app(): middleware, CORS, lifespan, /api/health
│   ├── endpoints.py        # search, library, streaming, logs routes
│   ├── auth_routes.py      # /api/auth/*
│   └── errors.py           # {"detail": {"code", "message"}} error model
├── services/
│   ├── auth.py             # AuthService, CredentialStore, cookie filtering, SAPISIDHASH
│   ├── youtube.py          # YouTubeService (ytmusicapi wrapper)
│   ├── extractor.py        # StreamExtractor (yt-dlp, single-flight, caches)
│   └── streaming/
│       ├── service.py      # StreamingService facade + singleton
│       ├── registry.py     # SegmentRegistry: per-segment state machine
│       ├── downloader.py   # DownloadManager (priority heap + workers), fetch_segment()
│       ├── cache.py        # CacheStore: files, layout.json, LRU, reconciliation
│       ├── serving.py      # HTTP Range → segment files
│       └── playback.py     # PlaybackSession, buffer_plan()
├── database/
│   ├── models.py           # Song, Playlist, PlaylistSong, LikedSong, Segment
│   └── session.py          # engine (WAL, busy_timeout), init_db(), session_scope()
├── utils/
│   ├── mp4.py              # fMP4 box + sidx parser (pure)
│   ├── layout.py           # SegmentInfo, StreamInfo, byte-range math (pure)
│   └── logger.py           # rotating files + in-memory ring buffer
└── tests/                  # pytest: unit (mocked) + integration (network)
```

## Frontend — `amp/frontend/`

```
frontend/
├── index.html              # CSP meta, favicons
├── public/                 # favicons, site.webmanifest
├── src/
│   ├── main.tsx            # initBackend() then render
│   ├── App.tsx             # layout: sidebar, routes, PlayerBar
│   ├── api.ts              # typed fetch client, base URL, ApiError
│   ├── sidecar.ts          # backend client: port, health poll, backend logs
│   ├── authSession.ts      # shared sign-in status (sidebar badge, 401 handling)
│   ├── tauri_auth.ts       # calls the youtube_login command
│   ├── state.ts            # queue + playback store (useSyncExternalStore)
│   ├── styles.css          # dark theme
│   ├── components/
│   │   ├── PlayerBar.tsx   # audio element, load sequence, segment bar
│   │   ├── SongList.tsx    # clickable song list
│   │   └── SignInPrompt.tsx
│   ├── player/             # pure helpers (vitest): errors, persistence, prefetch
│   └── pages/              # Search, Library, Playlists, Auth, Logs
└── src-tauri/
    ├── tauri.conf.json     # window, CSP, bundle, externalBin
    ├── Cargo.toml
    ├── capabilities/default.json   # core:default only
    ├── icons/
    ├── binaries/           # amp-backend-<triple>[.exe] (built, gitignored)
    └── src/
        ├── main.rs         # plugins, setup → backend::start, exit → backend::stop
        ├── backend.rs      # spawns, watches and stops the backend
        └── youtube_login.rs  # sign-in webview, reads cookies
```
