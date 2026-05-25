# AMP

Another Music Player : a local music player based on Youtube Music library.

## Description

**Features**
- Browse the Youtube library :
  - get playlists, get artist infos, get playlists and titles...
  - access artist, name, album, album art, lyrics (fetched from multiple provider sources).
  - The library is searchable by title, artist, album, playlists, and genre.
- Queue feature : 
  - build music queues
  - save queues locally
  - a queue might be "infinite" : it has a specific number of titles but when requested we can fetch new titles and add them to the queue. It can be done automatically (e.g. there are only 10 titles remaining before the end so we fetch additional titles to the queue), or manually (e.g. the user scrolls down the queue so we fetch additional titles).
- Local databases : 
  - userdb : store the saved queues, listening history, liked items (if not connected to an account). Persistent database.
  - playdb : stores the current queue, the current song (with infos like when are we on the song, etc), metadata that are displayed on the queue, etc. Usually flushed when the app restarts, but we might want to restore it sometimes.
  - chunkdb : stores the audio chunks for the listening queue. Flushed when the app starts.
- Fetch audio chunks from Youtube and play them.
- Control the music : play a queue
  - play/pause, shuffle titles in the queue, repeat the queue, repeat a single title
- Manage the sound : control the volume, EQ feature.
- Caching on a local database.
- Frontend : React.js web app, with an Electron.js wrapper to get a Desktop app.
- Authentification to Youtube for liking titles and editing playlists.
- Available in Linux and Windows.

**Play flow**
- When the selects an item (song, playlist, artist, album, etc), a queue is loaded, and chunks starts to be downloaded on the database.
- The database has a specific size, and must retain at least the current song, the next song and the previous song. If there is additional space, we fetch next songs.
- When the playback switch to ON, the player reads the queue, fetch the next audio chunks to play and play them.
- Once a chunk has been played we keep it until it can be removed from the cache.
- Every second we update the playdb so that we know at which point of the music we are.
- When the user change the title, or if the song is over, the queue is updated, the current play index changes to point to the next title.

**Miscancellous**
- logs are kept for debugging, we can also display warning/error logs on a page in the app.
- configuration : a JSON file is used for the coniguration. It can be updated manually, or later from the app frontend.
- the electron app wraps both the backend and the frontend, so there is nothing to install for user selecting this option.

## Development process

### Install dependencies

This tool is based on:
- `yt-dlp` : to download the music content
- `ytmusicapi` : to access youtube database
- `flask` : for the server backend
- `sql` : for the database
- ... (react, electron)

First install these python packages :
```bash
pip install yt-dlp ytmusicapi flask flask-cors sqlalchemy
```

### Code structure

```bash
amp/
├── backend/
│   ├── __init__.py
│   ├── music_library.py           # Handles yt-dlp downloads, ytmusicapi integration, local database storage
│   ├── playback_manager.py        # Manages streaming chunks, playback position tracking
│   └── api_server.py              # Flask REST API
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── styles.css
└── config.py
```

### API endpoints

Here are the key API endpoints :
- No auth required :
  - `GET /search` : Search (songs, artists, albums, playlists, genres)
  - `POST /select/{id}` : Select an item (title, artist, album, playlist, genre) to build the current queue.
  - `GET /queue` : Get infos on the current queue : name, titles, etc
  - `POST /play` : Start playback
  - `GET /status` : Current playback status. Infos : current playback time, cache status, queue name, title, album, etc
- Auth required :
  - `POST /auth` : YouTube authentication
  - `GET /uplaylists` : Get user playlists

### Database Schema

```sql
CREATE TABLE songs (
    id INTEGER PRIMARY KEY,
    title TEXT,
    artist TEXT,
    album TEXT,
    duration INTEGER,
    thumbnail TEXT,
    youtube_id TEXT,
    file_path TEXT,
    cached BOOLEAN DEFAULT FALSE
);
```

## Roadmap

### 1. Backend Core

Tasks :
- [ ] Basic Flask server setup
- [ ] Database schema implementation

### 2. Youtube implementation

Tasks :
- [ ] yt-dlp/ytmusicapi integration
- [ ] Authentication flow

At this point :
- I will have python functions to :
  - Search music (and artists, albums, songs, etc)
  - Get metadata from songs, artists, albums
  - Authentificate to an account
  - Get access to the user playlists, liked musics.
  - Be able to update playlists, like new titles. 
- I will be able to use the REST API through commands :
  - Everything described above will be accessible from the REST API.
  - Update every databases :
    - Update the listening history
    - Create and store queues in the userdb database
    - Get and update the playdb : add song to queue, get status, etc

### 3. Core playback system

Tasks :
- [ ] Early chunk cache
- [ ] Temporary player
- [ ] Basic playback manager
- [ ] Chunk streaming implementation

At this point I will have :
- A way to fetch audio chunks and to store them in the chunk database
- A super simple player that can read an audio chunk (and then a sequence of audio chunks)
- An interface (likely command line) to control the player :
  - Init : load a queue
  - Fetch : fetch the chunks cache
  - Once the whole cache is fetched I can :
    - Pause/Play
    - Forward : skip to next song 
    - Backward  go to the start of the current song (or to the previous song if we are on the first 5 seconds of the song)
    - Set the current playback timecode

### 4. Real-time chunk fetching

Tasks :
- [ ] Fetch chunks while playing

At this point :
- I have a buttont to load the queue
- The chunk fetching automatically starts
- Play button : the queue starts
- Chunks are constantly fetched
- If the playback reach the end of the fetched chunks
  - the player don't stop
  - Buffer ahead (at least 1sec after the current timecode) to ensure seamless playback
- If there are too much chunks download errors we stop the playback.
- We can see the warn/error logs

### 5. Playback Frontend 

Tasks :
- [ ] React UI components
- [ ] API integration
- [ ] Playback controls

At this point :
- We have a web interface
- We only see a pre-defined queue here
- We have most controls on the playback (play/pause, set timecode, next song, previous song)
- We can visualize the queue, scoll tosee next songs

### 6. Library management on the frontend

- [ ] Library browsing
- [ ] Authentification

At this point I will be able to :
- Browse library through a search bar on the UI.
- See results, click on a song/artist/album to explore infos.
- Add songs to a queue
- Visualize the songs in the queue, and the current selected song
- Launch the playback, get the playback infos from the UI
- Authentificate from the UI

### 7. Electron Wrapper

Tasks :
- [ ] Desktop app packaging
- [ ] Local server startup

At this point I will be able to :
- Install the desktop app
- Open the app
- Browse the library
- Start playback
- Listen to music
- Etc

### 8. Testing & Polish

- Error handling
- Cross-platform testing
- Performance optimization
