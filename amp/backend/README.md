# AMP Backend

FastAPI-based backend server for AMP (Another Music Player).

---

## 🐍 Virtual Environment

This project uses a **Python virtual environment** (`venv/`) for dependency isolation.

### Activate Before Use

From the project root (`AMP/`):
```cmd
activate.bat         # Windows CMD
# or
./activate.ps1       # Windows PowerShell
# or
venv\Scripts\activate
```

Your prompt should show `(venv)` when active.

---

## 📁 Project Structure

```bash
amp/backend/
├── __init__.py
├── main.py                  # Entry point to run the server
├── config.py               # Application configuration
├── .env.example             # Example environment variables
├── requirements.txt         # Python dependencies
├── database/
│   ├── __init__.py
│   ├── models.py            # SQLAlchemy database models (10 tables)
│   └── session.py           # Database session management
├── services/
│   ├── __init__.py
│   ├── youtube.py           # YouTube Music API (ytmusicapi)
│   ├── auth.py              # Cookie-based auth service (single source of truth)
│   └── streaming.py         # Audio streaming (yt-dlp)
├── api/
│   ├── __init__.py
│   ├── server.py            # FastAPI app setup
│   ├── endpoints.py         # REST API endpoints (search, queue, playback, user)
│   └── auth_routes.py       # Auth endpoints (status, cookies, import-browser, logout)
├── utils/
│   ├── __init__.py
│   └── logger.py            # Logging configuration
└── tests/
    ├── __init__.py
    ├── test_models.py       # Unit tests for models
    ├── test_endpoints.py    # Integration tests for endpoints
    ├── test_youtube.py      # YouTube service tests (28 tests)
    ├── test_streaming.py    # Streaming service tests (25 tests)
    ├── test_ytm_auth.py     # Auth service tests (11 tests)
    └── README.md            # Test instructions
```

---

## 🚀 Quick Start

### 1. Install Dependencies

From the project root (`AMP/`):

```bash
# Activate virtual environment
activate.bat          # Windows CMD
# or
./activate.ps1        # Windows PowerShell

# Install dependencies
pip install -r amp/backend/requirements.txt
```

### 2. Run the Server

```bash
# From project root, with venv activated
python amp/backend/main.py

# Or with custom host/port
python amp/backend/main.py --host 0.0.0.0 --port 8000

# With auto-reload on code changes
python amp/backend/main.py --reload
```

The server starts at **http://localhost:8000**
- API Docs (Swagger): http://localhost:8000/docs
- API Docs (ReDoc): http://localhost:8000/redoc
- Health Check: http://localhost:8000/api/health

---

## 📋 API Endpoints

### Health & Status
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |

### Authentication (Cookie-based)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/auth/status` | Get auth status (`?verify=true` to validate with YouTube) |
| POST | `/api/auth/cookies` | Receive cookies from Tauri sign-in window |
| POST | `/api/auth/import-browser` | Import cookies from installed browser (Firefox, Chrome, etc.) |
| POST | `/api/auth/logout` | Clear auth session |

### Library
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/search?q={query}&type={all\|song\|artist\|album\|playlist}&limit={n}` | Search YouTube Music |
| GET | `/api/song/{id}` | Get song metadata |
| GET | `/api/artist/{id}` | Get artist info |
| GET | `/api/album/{id}` | Get album info |
| GET | `/api/playlist/{id}` | Get playlist info |

### Queue
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/queue/select` | Select an item to build the queue |
| GET | `/api/queue` | Get current queue |

### Playback
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/queue/play` | Start playback |
| POST | `/api/queue/pause` | Pause playback |
| POST | `/api/queue/next` | Skip to next track |
| POST | `/api/queue/previous` | Go to previous track |
| POST | `/api/queue/seek?position_ms={ms}` | Seek to position |
| GET | `/api/playback/status` | Get playback status |
| POST | `/api/playback/position?position_ms={ms}` | Update playback position |

### User (Auth Required)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/user/playlists` | Get user's YouTube Music playlists |
| GET | `/api/user/likes` | Get user's liked songs |
| POST | `/api/user/likes?song_id={id}` | Like a song |

---

## 🔐 Authentication

AMP uses **cookie-based authentication** with YouTube Music. No Google Cloud OAuth credentials are needed.

### How it works

1. User connects via browser import (`/api/auth/import-browser`) or Tauri sign-in window
2. Backend validates cookies against YouTube Music
3. Session is saved to `.amp/cache/ytm_session.json` (0600 permissions)
4. All services share a single `AuthService` instance

### Quick auth test

```bash
# Import cookies from Firefox
curl -X POST http://localhost:8000/api/auth/import-browser \
  -H "Content-Type: application/json" \
  -d '{"browser": "firefox"}'

# Check status
curl http://localhost:8000/api/auth/status

# Get liked songs
curl http://localhost:8000/api/user/likes
```

See [AUTH_FLOW_GUIDE.md](../../AUTH_FLOW_GUIDE.md) for detailed auth documentation.

---

## 🧪 Testing

### Run Tests

From the project root, with venv activated:

```bash
# Run all tests (92 tests)
pytest amp/backend/tests/ -v

# Run with coverage
pytest amp/backend/tests/ --cov=amp.backend --cov-report=term

# Run specific test file
pytest amp/backend/tests/test_ytm_auth.py -v
pytest amp/backend/tests/test_youtube.py -v
pytest amp/backend/tests/test_streaming.py -v
```

See [tests/README.md](tests/README.md) for detailed test instructions.

---

## 🗃️ Database Models

### UserDB (Persistent)
| Table | Description |
|-------|-------------|
| `songs` | Song metadata from YouTube |
| `playlists` | Playlists (YouTube or local) |
| `playlist_songs` | Playlist-Song relationships |
| `queues` | User-created or generated queues |
| `queue_items` | Items in queues |
| `user_history` | Listening history |
| `liked_songs` | Liked songs per user |
| `saved_queues` | Saved queues per user |
| `cached_chunks` | Metadata for cached audio chunks |

### PlayDB (Session)
| Table | Description |
|-------|-------------|
| `playback_state` | Current playback state |

---

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `fastapi` | Web framework |
| `uvicorn` | ASGI server |
| `sqlalchemy` | ORM for SQLite |
| `pydantic-settings` | Configuration management |
| `yt-dlp` | YouTube audio downloading/streaming |
| `ytmusicapi` | YouTube Music metadata API |
| `pytest` | Testing framework |

---

## 🔧 Configuration

Configuration is loaded from:
1. Environment variables
2. `.env` file (if it exists)
3. Defaults in `config.py`

### Main Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `APP_NAME` | `AMP Backend` | Application name |
| `APP_VERSION` | `0.1.0` | Application version |
| `DEBUG` | `True` | Enable debug mode |
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8000` | Server port |
| `USERDB_PATH` | `userdb.sqlite` | Path to userdb SQLite file |
| `PLAYDB_PATH` | `playdb.sqlite` | Path to playdb SQLite file |
| `CACHE_MAX_SIZE_MB` | `500` | Maximum cache size in MB |
| `CHUNK_SIZE_SEC` | `10` | Chunk duration in seconds |
| `BUFFER_AHEAD_SEC` | `15` | Buffer ahead time in seconds |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FILE` | `.amp/logs/app.log` | Log file path |

---

## 📂 File Locations

| File/Dir | Purpose | Location |
|----------|---------|----------|
| `userdb.sqlite` | Persistent database | Project root |
| `playdb.sqlite` | Session database | Project root |
| `.amp/cache/chunks/` | Audio chunk cache | Hidden directory |
| `.amp/cache/ytm_session.json` | Saved auth session (0600) | Hidden directory |
| `.amp/logs/app.log` | Application logs | Hidden directory |

---

## 🐛 Troubleshooting

### "Module not found" errors
Ensure you're running commands from the **project root** (`AMP/`), with the venv activated.

### Port already in use
```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux/Mac
lsof -i :8000
kill -9 <PID>
```

### SQLite lock errors
Make sure no other instance of the app is running.

### yt-dlp/ytmusicapi errors
Ensure you have the latest versions:
```bash
pip install --upgrade yt-dlp ytmusicapi
```

### Auth issues
- Chrome on Windows may be blocked by app-bound encryption → use Firefox
- Session expired → re-import or re-login
- See [AUTH_FLOW_GUIDE.md](../../AUTH_FLOW_GUIDE.md) for details

---

## 📚 Documentation

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [SQLAlchemy Docs](https://www.sqlalchemy.org/)
- [yt-dlp Docs](https://github.com/yt-dlp/yt-dlp)
- [ytmusicapi Docs](https://ytmusicapi.readthedocs.io/)
- [Auth Flow Guide](../../AUTH_FLOW_GUIDE.md)
