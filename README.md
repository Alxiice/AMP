# AMP

Another Music Player: a local music player based on YouTube Music library.

---

## Description

**Features**
- **Browse the YouTube library**:
  - Get playlists, artist infos, albums, and titles.
  - Access artist, name, album, album art, lyrics (fetched from multiple provider sources).
  - The library is searchable by title, artist, album, playlists, and genre.
- **Queue feature**:
  - Build music queues.
  - Save queues locally.
  - A queue might be "infinite": it has a specific number of titles, but when requested, we can fetch new titles and add them to the queue. This can be done automatically (e.g., there are only 10 titles remaining before the end, so we fetch additional titles) or manually (e.g., the user scrolls down the queue).
- **Local storage**:
  - **`userdb`** (SQLite): Store saved queues, listening history, liked items (if not connected to an account). Persistent database.
  - **`playdb`** (SQLite): Stores the current queue, the current song (with infos like playback position, etc.), metadata displayed on the queue, etc. Usually flushed when the app restarts, but can be restored if needed.
  - **`chunk cache`** (filesystem): Stores audio chunks in `.amp/cache/chunks/` as temporary files (e.g., `{youtube_id}_{start}-{end}.mp3`). Automatically cleaned up when space exceeds a limit or chunks expire.
- **Fetch audio chunks from YouTube** and stream them to the frontend.
- **Control the music**: Play a queue with:
  - Play/pause, shuffle titles in the queue, repeat the queue, repeat a single title.
- **Manage the sound**: Control the volume, EQ feature (via Web Audio API).
- **Caching**: Local cache for chunks, metadata, and thumbnails.
- **Frontend**: React.js web app, with a **Tauri** wrapper for Desktop (Linux, Windows) and future Android support (Tauri 2.0).
- **Authentication**: YouTube OAuth for liking titles and editing playlists.
- **Available on**: Linux, Windows (Desktop), and potentially Android (via Tauri 2.0).

---

## Technical Decisions

### Backend
- **FastAPI**: Async-native, better performance for streaming endpoints, auto-generated OpenAPI docs.
- **yt-dlp**: Download/stream audio from YouTube.
- **ytmusicapi**: Access YouTube Music metadata (search, artists, albums, playlists).

### Frontend
- **React.js**: Web UI for library browsing, queue management, and playback controls.
- **Web Audio API**: Handles playback, buffering, EQ, and volume control in the browser.
- **Tauri**: Lightweight desktop wrapper. Enables future Android support (Tauri 2.0).

### Storage
- **SQLite**: For structured data (songs, playlists, queues, user history).
- **Filesystem**: For audio chunks (faster I/O than SQLite BLOBs). Chunks are stored in `.amp/cache/chunks/` and automatically cleaned up.

### Playback Architecture
- **Frontend-managed playback**: The backend streams chunks via HTTP (`GET /stream/{song_id}`), and the frontend buffers/plays them using the Web Audio API.
- **No backend audio processing**: The backend only fetches and streams chunks; the frontend handles buffering, playback, EQ, and volume.

---

## Play Flow

1. **User selects an item** (song, playlist, artist, album, etc):
   - A queue is loaded.
   - The backend starts fetching chunks for the current, next, and previous songs.
2. **Chunk storage**:
   - Chunks are stored as files in `.amp/cache/chunks/`.
   - The cache has a **size limit** (e.g., 500MB) and retains at least the current song + next + previous song.
3. **Playback starts**:
   - The frontend requests chunks via HTTP streaming (`GET /stream/{song_id}`).
   - The frontend buffers chunks using the Web Audio API.
4. **During playback**:
   - Chunks are fetched **ahead of time** (e.g., 10 seconds of buffer).
   - Once a chunk is played, it remains in cache until evicted by LRU (Least Recently Used) or space constraints.
5. **Position tracking**:
   - Every second, the frontend updates the backend with the current playback time (`POST /playback/position`).
6. **Song transitions**:
   - When the user skips or a song ends, the queue advances, and the frontend requests chunks for the new song.

---

## Miscellaneous

- **Logs**: Kept for debugging. Warning/error logs can be displayed on a dedicated page in the app.
- **Configuration**: A JSON file (`config.json`) stores settings (e.g., cache size, audio quality, theme). Can be updated manually or via the frontend.
- **Tauri app**: Wraps the backend (Python) and frontend (React) into a single executable. No additional installations required for users.

---

## Development Process

### Install Dependencies

This project uses:
- `yt-dlp`: Download/stream music content from YouTube.
- `ytmusicapi`: Access YouTube Music metadata.
- **FastAPI**: Backend server.
- **Uvicorn**: ASGI server for FastAPI.
- **SQLAlchemy**: ORM for SQLite databases.
- **React.js**: Frontend UI.
- **Tauri**: Desktop and mobile app wrapper.

First, install Python dependencies:
```bash
pip install yt-dlp ytmusicapi fastapi uvicorn sqlalchemy python-multipart
```

For the frontend (React + Tauri), see [Frontend Setup](#).

---

### Code Structure

```bash
amp/
├── backend/
│   ├── __init__.py
│   ├── config.py               # App configuration (cache size, API keys, etc.)
│   ├── database/
│   │   ├── __init__.py
│   │   ├── models.py           # SQLAlchemy models (songs, playlists, queues, etc.)
│   │   └── session.py          # Database session management
│   ├── services/
│   │   ├── youtube.py          # yt-dlp and ytmusicapi integration
│   │   ├── library.py          # Library management (search, metadata, etc.)
│   │   ├── queue.py            # Queue management (build, modify, persist)
│   │   └── auth.py             # YouTube OAuth flow
│   ├── utils/
│   │   ├── cache.py            # Chunk cache management (filesystem)
│   │   ├── streaming.py        # Chunk streaming logic
│   │   └── logger.py           # Logging setup
│   └── api/
│       ├── __init__.py
│       ├── endpoints.py        # FastAPI routes (search, queue, playback, etc.)
│       └── server.py           # FastAPI app setup
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── components/         # React components
│   │   ├── hooks/              # Custom hooks (e.g., usePlayback, useQueue)
│   │   ├── services/           # API clients, Web Audio API wrapper
│   │   ├── styles/             # CSS/SCSS
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── tauri.conf.json         # Tauri configuration
├── .amp/                       # Hidden directory for cache and logs
│   ├── cache/
│   │   └── chunks/             # Audio chunk files (e.g., {id}_0-10.mp3)
│   └── logs/
│       └── app.log             # Application logs
└── config.json                 # User configuration
```

---

### API Endpoints

**No auth required**:
- `GET /api/search?q={query}&type={all|song|artist|album|playlist}`: Search YouTube Music.
- `GET /api/song/{id}`: Get song metadata (title, artist, album, thumbnail, etc.).
- `GET /api/artist/{id}`: Get artist info (bio, top tracks, albums, etc.).
- `GET /api/album/{id}`: Get album info (tracks, artwork, etc.).
- `GET /api/playlist/{id}`: Get playlist info (tracks, owner, etc.).
- `POST /api/queue/select`: Select an item (song, artist, album, playlist) to build the current queue.
- `GET /api/queue`: Get current queue info (name, tracks, etc.).
- `POST /api/queue/play`: Start playback.
- `POST /api/queue/pause`: Pause playback.
- `POST /api/queue/next`: Skip to next track.
- `POST /api/queue/previous`: Go to previous track.
- `POST /api/queue/seek`: Seek to a specific position in the current track.
- `GET /api/playback/status`: Get current playback status (time, queue name, track, album, buffer status).
- `GET /api/stream/{song_id}`: Stream audio chunks for a song (frontend buffers via Web Audio API).

**Auth required**:
- `POST /api/auth/login`: Initiate YouTube OAuth flow.
- `POST /api/auth/callback`: Handle OAuth callback.
- `GET /api/user/playlists`: Get user’s YouTube playlists.
- `POST /api/user/playlists/{id}/add`: Add a song to a user playlist.
- `POST /api/user/playlists/{id}/remove`: Remove a song from a user playlist.
- `POST /api/user/likes`: Like/unlike a song.
- `GET /api/user/likes`: Get user’s liked songs.

---

### Database Schema

All tables are stored in SQLite (`userdb` for persistent data, `playdb` for session data).

#### Core Tables
```sql
-- Songs (metadata from YouTube Music)
CREATE TABLE songs (
    id TEXT PRIMARY KEY,              -- YouTube video ID
    title TEXT NOT NULL,
    artist TEXT,
    album TEXT,
    duration_ms INTEGER,             -- Duration in milliseconds
    thumbnail_url TEXT,
    lyrics TEXT,
    year INTEGER,
    genre TEXT,
    bitrate INTEGER,
    sample_rate INTEGER,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Playlists (YouTube or local)
CREATE TABLE playlists (
    id TEXT PRIMARY KEY,              -- YouTube playlist ID or local UUID
    name TEXT NOT NULL,
    description TEXT,
    owner TEXT,                       -- User ID or "local"
    is_youtube BOOLEAN DEFAULT FALSE,
    thumbnail_url TEXT,
    song_count INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Playlist-Song relationships
CREATE TABLE playlist_songs (
    playlist_id TEXT,
    song_id TEXT,
    position INTEGER,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (playlist_id, position),
    FOREIGN KEY (playlist_id) REFERENCES playlists(id),
    FOREIGN KEY (song_id) REFERENCES songs(id)
);

-- Queues (user-created or generated)
CREATE TABLE queues (
    id TEXT PRIMARY KEY,              -- UUID
    name TEXT,
    is_infinite BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Queue items
CREATE TABLE queue_items (
    queue_id TEXT,
    song_id TEXT,
    position INTEGER,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (queue_id, position),
    FOREIGN KEY (queue_id) REFERENCES queues(id),
    FOREIGN KEY (song_id) REFERENCES songs(id)
);
```

#### Playback State (`playdb`)
```sql
-- Current playback state (reset on app restart unless restored)
CREATE TABLE playback_state (
    current_queue_id TEXT,
    current_song_id TEXT,
    current_time_ms INTEGER,          -- Playback position in ms
    is_playing BOOLEAN DEFAULT FALSE,
    volume REAL DEFAULT 1.0,
    repeat_mode TEXT CHECK(repeat_mode IN ('none', 'all', 'one')),
    shuffle BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### User Data (`userdb`)
```sql
-- Listening history
CREATE TABLE user_history (
    user_id TEXT,
    song_id TEXT,
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    duration_ms INTEGER,              -- How long the song was played
    PRIMARY KEY (user_id, song_id, played_at),
    FOREIGN KEY (song_id) REFERENCES songs(id)
);

-- Liked songs
CREATE TABLE liked_songs (
    user_id TEXT,
    song_id TEXT,
    liked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, song_id),
    FOREIGN KEY (song_id) REFERENCES songs(id)
);

-- Saved queues (user-created)
CREATE TABLE saved_queues (
    user_id TEXT,
    queue_id TEXT,
    saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, queue_id),
    FOREIGN KEY (queue_id) REFERENCES queues(id)
);
```

#### Chunk Cache Metadata
```sql
-- Metadata for cached chunks (files are stored in .amp/cache/chunks/)
CREATE TABLE cached_chunks (
    song_id TEXT,
    start_ms INTEGER,               -- Start time in ms
    end_ms INTEGER,                 -- End time in ms
    file_path TEXT NOT NULL,        -- Path to the chunk file
    size_bytes INTEGER,            -- File size
    last_accessed TIMESTAMP,        -- For LRU cleanup
    expires_at TIMESTAMP,          -- Optional expiry time
    PRIMARY KEY (song_id, start_ms),
    FOREIGN KEY (song_id) REFERENCES songs(id)
);
```

---

## Roadmap

### 1. Backend Core
**Tasks**:
- [ ] FastAPI server setup with Uvicorn.
- [ ] SQLite database initialization with SQLAlchemy.
- [ ] Base models for `songs`, `playlists`, `queues`.

**At this point**:
- A running FastAPI server with basic endpoints (`/api/search`, `/api/song/{id}`).
- SQLite databases (`userdb`, `playdb`) initialized.

---

### 2. YouTube Integration
**Tasks**:
- [ ] `yt-dlp` integration for audio streaming.
- [ ] `ytmusicapi` integration for metadata (search, artists, albums, playlists).
- [ ] YouTube OAuth flow for user authentication.

**At this point**:
- Python functions to:
  - Search music, artists, albums, playlists.
  - Get metadata for songs, artists, albums.
  - Authenticate with YouTube and access user playlists/liked songs.
  - Update playlists and like/unlike titles.
- All functionality exposed via REST API.
- Databases updated for:
  - Listening history.
  - Saved queues in `userdb`.
  - Playback state in `playdb`.

---

### 3. Core Playback System
**Tasks**:
- [ ] Chunk cache manager (filesystem-based in `.amp/cache/chunks/`).
- [ ] FastAPI streaming endpoint (`GET /stream/{song_id}`).
- [ ] Basic playback controls (play/pause, next, previous, seek).

**At this point**:
- Backend can fetch and stream audio chunks on demand.
- Frontend can request chunks via HTTP and buffer them (minimal Web Audio API integration).
- Playback controls work via API calls.

---

### 4. Frontend Buffering & Playback
**Tasks**:
- [ ] Web Audio API integration for chunk buffering/playback.
- [ ] Playback position tracking (update backend every second).
- [ ] Volume and EQ controls.

**At this point**:
- Frontend can:
  - Buffer chunks in memory.
  - Play audio seamlessly.
  - Handle play/pause, next/previous, seek, volume, EQ.
- Backend provides chunk streaming and state management.

---

### 5. Real-Time Chunk Fetching
**Tasks**:
- [ ] Automatic chunk fetching during playback.
- [ ] Buffer-ahead logic (maintain 10s+ of audio buffer).
- [ ] Error handling for failed chunk fetches.

**At this point**:
- Chunks are fetched automatically as playback progresses.
- Playback never stops if the network is stable.
- Failed fetches trigger retries or skips (configurable).
- Warnings/errors are logged and visible in the app.

---

### 6. Playback Frontend
**Tasks**:
- [ ] React UI components for playback controls.
- [ ] Queue visualization (scrollable list of tracks).
- [ ] Now-playing panel (current track, album art, progress bar).

**At this point**:
- A functional web interface with:
  - Playback controls (play/pause, next, previous, seek, volume, EQ).
  - Queue display (current track highlighted, scrollable).
  - Now-playing info (title, artist, album, artwork).

---

### 7. Library Management Frontend
**Tasks**:
- [ ] Library browsing UI (search bar, results, filters).
- [ ] Artist/album/song detail pages.
- [ ] Authentication UI (YouTube OAuth).

**At this point**:
- Users can:
  - Search the YouTube Music library.
  - Browse results and explore artist/album/song details.
  - Add songs/playlists to queues.
  - Authenticate with YouTube.
- Playback and library management are fully integrated.

---

### 8. Tauri Desktop App
**Tasks**:
- [ ] Tauri configuration for desktop (Linux, Windows).
- [ ] Backend/frontend bundling (Tauri + Python).
- [ ] Auto-start backend server on app launch.

**At this point**:
- A installable desktop app that:
  - Bundles the backend (Python) and frontend (React).
  - Auto-starts the FastAPI server on launch.
  - Opens the React UI in a native window.
- Users can browse, queue, and play music without additional setup.

---

### 9. Android Support (Tauri 2.0)
**Tasks**:
- [ ] Tauri mobile configuration.
- [ ] Backend compatibility adjustments (if needed).
- [ ] UI adjustments for mobile.

**At this point**:
- An APK that can be installed on Android devices.
- Full functionality (library browsing, playback, etc.) on mobile.

---

### 10. Testing & Polish
**Tasks**:
- [ ] Error handling (network issues, YouTube API limits, etc.).
- [ ] Cross-platform testing (Linux, Windows, Android).
- [ ] Performance optimization (chunk size, buffer size, caching).
- [ ] UI/UX polish (animations, themes, accessibility).

---

## Configuration

The app uses a `config.json` file for settings:

```json
{
  "cache": {
    "max_size_mb": 500,
    "chunk_size_sec": 10,
    "buffer_ahead_sec": 15
  },
  "audio": {
    "quality": "high",
    "format": "mp3",
    "bitrate": 192
  },
  "playback": {
    "default_volume": 0.8,
    "eq_enabled": true
  },
  "youtube": {
    "api_key": "",
    "oauth": {
      "client_id": "",
      "client_secret": ""
    }
  },
  "logging": {
    "level": "info",
    "file": ".amp/logs/app.log"
  }
}
```
