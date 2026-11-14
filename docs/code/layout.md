# Repository layout

```
(repo root)
├── README.md                    # what AMP is + how to launch it
├── LICENSE                      # MIT + no-affiliation / liability notice
├── CHANGELOG.md                 # release notes (used by the Release workflow)
├── mkdocs.yml, docs/            # this documentation
├── AGENTS.md                    # progress tracker: revisions, decisions, known issues
├── DESIGN_DOC.md                # design spec, incl. the pitfall list P1–P31
├── TASKS.md                     # open work and proposals
├── AMP.bat                      # Windows: starts the app in dev mode (npm run tauri dev)
├── overrides/home.html          # docs home page template (MkDocs Material)
├── icon/                        # logo-square.svg, logo-round.svg
├── .github/workflows/           # python-ci.yml, tauri-build.yml, docs.yml, release.yml
├── .ruff.toml                   # lint rules
├── build/                       # build_release.py output (gitignored)
└── amp/                         # the application
    ├── backend/                 # Python package (FastAPI)
    ├── frontend/                # React app + src-tauri/ (Rust shell)
    ├── scripts/
    │   ├── build_release.py     # full build: sidecar + Tauri → <repo>/build/
    │   ├── build_sidecar.py     # PyInstaller → src-tauri/binaries/ (+ --smoke)
    │   ├── docs_screenshots.mjs # docs screenshots (headless Edge over CDP)
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
├── widget.py, widget.html  # OBS now-playing widget server (own port)
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
│   ├── models.py           # Song, LikedSong, SavedQueue, ListeningHistory, Segment
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
│   ├── settings.ts         # theme, accent, crossfade, normalization
│   ├── likes.ts, savedQueues.ts, albumNav.ts, ui.ts, format.ts
│   ├── styles.css          # design tokens (dark + light) and components
│   ├── components/
│   │   ├── PlayerBar.tsx   # two audio elements, load sequence, crossfade, segment bar, media session
│   │   ├── QueuePanel.tsx  # play queue (drag, menu, shuffle, repeat, save)
│   │   ├── SongList.tsx, SongMenu.tsx, LikeButton.tsx, Cover.tsx, Icon.tsx
│   │   ├── CollectionHeader.tsx, SignInPrompt.tsx
│   │   └── UiLayer.tsx     # toasts and dialogs
│   ├── player/             # pure helpers (vitest): queue, errors, persistence, prefetch,
│   │                       # fade, normalize, history, keyboard
│   └── pages/              # NowPlaying, Search, Library, Playlists, PlaylistDetail, AlbumDetail,
│                           # SavedQueues, SavedQueueDetail, History, Settings, Auth, Developer, Logs
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
