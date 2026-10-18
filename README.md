<div align="center">
  <img src="./icon/logo-square.svg" width="200"/>
  <h1 style="font-size: value;">
    AMP <br/>
  </h1>
  <i>Another Music Player : a local music player based on Youtube Music library.

</i>
  <br/>
  <br/>
</div>

---

## Quick Start

```bash
# 1. Start the backend (from project root, with venv activated)
activate.bat && python amp/backend/main.py
# → http://localhost:8000

# 2. Start the web interface (new terminal)
cd app && npm install && npm run dev
# → http://localhost:1420

# 3. Connect YouTube Music (import cookies from Firefox)
curl -X POST http://localhost:8000/api/auth/import-browser \
  -H "Content-Type: application/json" -d '{"browser": "firefox"}'
```

See [AUTH_FLOW_GUIDE.md](AUTH_FLOW_GUIDE.md) for detailed auth instructions.

---

## Features

- **YouTube Music integration**: Search, browse artists/albums/playlists, get metadata
- **Cookie-based authentication**: Connect your YouTube Music account (no OAuth credentials needed)
- **Audio streaming**: yt-dlp powered chunk downloading and caching
- **Web interface**: React frontend (Vite dev server) — test without Tauri
- **Tauri desktop app**: Project structure ready (requires Rust build tools to compile)
- **Queue management**: Build, save, and play music queues
- **Local storage**: SQLite databases + filesystem chunk cache

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, Uvicorn, SQLAlchemy, SQLite |
| YouTube | ytmusicapi (metadata), yt-dlp (audio) |
| Frontend | React, TypeScript, Vite |
| Desktop | Tauri 2.x (structure ready) |
| Tests | pytest (92 tests) |

---

## Project Structure

```
AMP/
├── amp/backend/           # FastAPI backend
│   ├── api/               # REST endpoints + auth routes
│   ├── database/          # SQLAlchemy models + sessions
│   ├── services/          # youtube.py, auth.py, streaming.py
│   ├── utils/             # logger.py
│   ├── config.py          # Pydantic settings
│   ├── main.py            # Server entry point
│   └── tests/             # 92 tests
├── app/                   # React web interface
│   ├── src/               # App.tsx, useYouTubeAuth.ts, styles
│   └── src-tauri/         # Tauri desktop app (structure ready)
├── venv/                  # Python virtual environment
├── .amp/                  # Cache, logs, session data
├── ROADMAP.md             # Full project roadmap (12 phases)
├── AGENTS.md              # Agent/developer instructions
├── AUTH_FLOW_GUIDE.md     # Authentication documentation
└── IMPLEMENTATION_NOTES.md # Phase-by-phase implementation details
```

---

## API Endpoints

### Public
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/search?q={query}` | Search YouTube Music |
| GET | `/api/song/{id}` | Song metadata |
| GET | `/api/artist/{id}` | Artist info |
| GET | `/api/album/{id}` | Album info |
| GET | `/api/playlist/{id}` | Playlist info |
| POST | `/api/queue/select` | Build queue from item |
| GET | `/api/queue` | Current queue |
| POST | `/api/queue/play\|pause\|next\|previous\|seek` | Playback controls |
| GET | `/api/playback/status` | Playback state |

### Authentication (Cookie-based)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/auth/status` | Auth status (`?verify=true` to validate) |
| POST | `/api/auth/cookies` | Submit cookies from Tauri sign-in window |
| POST | `/api/auth/import-browser` | Import cookies from browser (Firefox, etc.) |
| POST | `/api/auth/logout` | Clear session |

### Auth Required
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/user/playlists` | User's YouTube Music playlists |
| GET | `/api/user/likes` | User's liked songs |
| POST | `/api/user/likes?song_id={id}` | Like a song |

Full API docs: http://localhost:8000/docs

---

## Documentation

| File | Description |
|------|-------------|
| [ROADMAP.md](ROADMAP.md) | Full 12-phase project roadmap |
| [AGENTS.md](AGENTS.md) | Developer/agent instructions |
| [AUTH_FLOW_GUIDE.md](AUTH_FLOW_GUIDE.md) | Cookie-based auth flow details |
| [IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md) | Phase 1 & 2 implementation details |
| [amp/backend/README.md](amp/backend/README.md) | Backend-specific guide |
| [app/README.md](app/README.md) | Frontend/web interface guide |
| [amp/backend/tests/README.md](amp/backend/tests/README.md) | Test suite documentation |

---

## Roadmap Summary

| Phase | Status |
|-------|--------|
| 1. Backend Core | ✅ Complete |
| 2. YouTube Integration (API, Auth, Web Interface) | ✅ Complete |
| **3. Core Playback System** | ⏳ **Next** |
| 4. Frontend Buffering | ⏳ |
| 5. Real-Time Chunk Fetching | ⏳ |
| 6. Playback Frontend | ⏳ |
| 7. Library Management Frontend | ⏳ |
| 8. Tauri Desktop App | ⏳ |
| 9. Android Support | ⏳ |
| 10. Testing & Polish | ⏳ |

See [ROADMAP.md](ROADMAP.md) for details.

---

## Configuration

```json
{
  "cache": { "max_size_mb": 500, "chunk_size_sec": 10, "buffer_ahead_sec": 15 },
  "audio": { "quality": "high", "format": "mp3", "bitrate": 192 },
  "playback": { "default_volume": 0.8, "eq_enabled": true },
  "logging": { "level": "info", "file": ".amp/logs/app.log" }
}
```
