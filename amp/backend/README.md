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

### Run Commands

All Python commands should be run from within the activated virtual environment:
```bash
# Run the server
python backend/main.py

# Run tests
pytest backend/tests/ -v
```

---

## 📁 Project Structure

```bash
backend/
├── __init__.py
├── main.py                  # Entry point to run the server
├── config.py               # Application configuration
├── .env.example             # Example environment variables
├── requirements.txt         # Python dependencies
├── database/
│   ├── __init__.py
│   ├── models.py            # SQLAlchemy database models
│   └── session.py           # Database session management
├── api/
│   ├── __init__.py
│   ├── server.py            # FastAPI app setup
│   └── endpoints.py         # REST API endpoints
├── utils/
│   ├── __init__.py
│   └── logger.py            # Logging configuration
└── tests/
    ├── __init__.py
    ├── test_models.py       # Unit tests for models
    ├── test_endpoints.py    # Integration tests for endpoints
    └── README.md            # Test instructions
```

---

## 🚀 Quick Start

### 1. Install Dependencies

From the project root (`AMP/`):

```bash
# Create virtual environment (recommended)
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt
```

### 2. Configure Environment

Copy the example environment file and customize if needed:

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` to set your preferred configuration (all values have sensible defaults).

### 3. Initialize Databases

The databases are automatically initialized when the server starts. You can also initialize them manually:

```bash
python -c "from backend.database.session import init_userdb, init_playdb; init_userdb(); init_playdb()"
```

This creates:
- `userdb.sqlite`: Persistent data (songs, playlists, queues, user history)
- `playdb.sqlite`: Session data (playback state)

### 4. Run the Server

```bash
# From project root
python backend/main.py

# Or with custom host/port
python backend/main.py --host 0.0.0.0 --port 8000

# With auto-reload on code changes
python backend/main.py --reload
```

The server will start at `http://0.0.0.0:8000`.

### 5. Access the API

- **API Docs (Swagger)**: `http://localhost:8000/docs`
- **API Docs (ReDoc)**: `http://localhost:8000/redoc`
- **Health Check**: `http://localhost:8000/api/health`

---

## 📋 API Endpoints

### Health & Status
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |

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

---

## 🧪 Testing

### Run Tests

From the project root:

```bash
# Run all tests
pytest backend/tests/ -v

# Run with coverage
pytest backend/tests/ --cov=backend --cov-report=term

# Run specific test file
pytest backend/tests/test_models.py -v
pytest backend/tests/test_endpoints.py -v

# Run specific test
pytest backend/tests/test_endpoints.py::TestHealthEndpoint::test_health_check -v
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
| `.amp/logs/app.log` | Application logs | Hidden directory |

---

## 🐛 Troubleshooting

### "Module not found" errors
Ensure you're running commands from the **project root** (`AMP/`), not from the `backend/` directory.

### Port already in use
```bash
# Linux/Mac
lsof -i :8000
kill -9 <PID>

# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### SQLite lock errors
Make sure no other instance of the app is running, and that you're not manually accessing the SQLite files.

### yt-dlp/ytmusicapi errors
Ensure you have the latest versions:
```bash
pip install --upgrade yt-dlp ytmusicapi
```

---

## 📚 Documentation

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [SQLAlchemy Docs](https://www.sqlalchemy.org/)
- [yt-dlp Docs](https://github.com/yt-dlp/yt-dlp)
- [ytmusicapi Docs](https://ytmusicapi.readthedocs.io/)
