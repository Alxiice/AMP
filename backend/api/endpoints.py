"""
FastAPI Endpoints
=================
REST API endpoints for AMP Backend.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional, List
from pydantic import BaseModel

from backend.utils.logger import get_logger
from backend.database.session import get_userdb_session, get_playdb_session
from backend.database.models import (
    Song,
    Playlist,
    Queue,
    PlaybackState,
    RepeatMode,
)

router = APIRouter(tags=["api"])
logger = get_logger(__name__)


# =============================================================================
# PYDANTIC MODELS (Request/Response)
# =============================================================================

class SongResponse(BaseModel):
    """Song metadata response."""
    id: str
    title: str
    artist: Optional[str] = None
    album: Optional[str] = None
    duration_ms: Optional[int] = None
    thumbnail_url: Optional[str] = None
    year: Optional[int] = None
    genre: Optional[str] = None


class PlaylistResponse(BaseModel):
    """Playlist response."""
    id: str
    name: str
    description: Optional[str] = None
    owner: str
    is_youtube: bool
    thumbnail_url: Optional[str] = None
    song_count: int


class QueueResponse(BaseModel):
    """Queue response."""
    id: str
    name: Optional[str] = None
    is_infinite: bool
    songs: List[SongResponse] = []


class PlaybackStatusResponse(BaseModel):
    """Current playback status."""
    current_queue_id: Optional[str] = None
    current_song_id: Optional[str] = None
    current_song: Optional[SongResponse] = None
    current_time_ms: int = 0
    is_playing: bool = False
    volume: float = 1.0
    repeat_mode: str = RepeatMode.NONE.value
    shuffle: bool = False


class SearchRequest(BaseModel):
    """Search request."""
    q: str  # Search query
    type: str = "all"  # all, song, artist, album, playlist
    limit: int = 20


class QueueSelectRequest(BaseModel):
    """Request to select an item for the queue."""
    item_type: str  # song, artist, album, playlist, genre
    item_id: str  # ID of the item to select


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "message": "AMP Backend is running"}


# -----------------------------------------------------------------------------
# Search & Library
# -----------------------------------------------------------------------------

@router.get("/search", response_model=List[SongResponse], tags=["library"])
async def search_songs(
    q: str = Query(..., description="Search query"),
    type: str = Query("all", description="Search type: all, song, artist, album, playlist"),
    limit: int = Query(20, description="Maximum results"),
):
    """
    Search YouTube Music library.
    
    For now, returns mock data. Will be implemented with ytmusicapi later.
    """
    logger.info(f"Search request: q='{q}', type='{type}', limit={limit}")
    
    # TODO: Implement with ytmusicapi
    # For now, return mock data
    mock_songs = [
        SongResponse(
            id="dQw4w9WgXcQ",
            title="Rick Astley - Never Gonna Give You Up",
            artist="Rick Astley",
            album="Whenever You Need Somebody",
            duration_ms=213000,
            thumbnail_url="https://i.ytimg.com/vi/dQw4w9WgXcQ/mqdefault.jpg",
            year=1987,
            genre="Pop"
        ),
        SongResponse(
            id="9bZkp7q1984",
            title="Gorillaz - Feel Good Inc.",
            artist="Gorillaz",
            album="Demon Days",
            duration_ms=224000,
            thumbnail_url="https://i.ytimg.com/vi/9bZkp7q1984/mqdefault.jpg",
            year=2005,
            genre="Alternative"
        ),
    ]
    
    return mock_songs[:limit]


@router.get("/song/{song_id}", response_model=SongResponse, tags=["library"])
async def get_song(song_id: str):
    """
    Get song metadata by ID.
    
    First checks local cache (userdb), then fetches from YouTube Music.
    """
    logger.info(f"Get song: id='{song_id}'")
    
    # Check local cache first
    db = next(get_userdb_session())
    song = db.query(Song).filter(Song.id == song_id).first()
    
    if song:
        logger.debug(f"Song found in cache: {song.title}")
        return SongResponse(
            id=song.id,
            title=song.title,
            artist=song.artist,
            album=song.album,
            duration_ms=song.duration_ms,
            thumbnail_url=song.thumbnail_url,
            year=song.year,
            genre=song.genre,
        )
    
    # TODO: Fetch from YouTube Music API (ytmusicapi)
    # For now, return mock data if not in cache
    logger.warning(f"Song not in cache: {song_id}")
    return SongResponse(
        id=song_id,
        title=f"Unknown Song ({song_id})",
        artist="Unknown Artist",
    )


@router.get("/artist/{artist_id}", tags=["library"])
async def get_artist(artist_id: str):
    """
    Get artist info by ID.
    
    TODO: Implement with ytmusicapi.
    """
    logger.info(f"Get artist: id='{artist_id}'")
    return {"id": artist_id, "name": f"Artist {artist_id}", "top_tracks": []}


@router.get("/album/{album_id}", tags=["library"])
async def get_album(album_id: str):
    """
    Get album info by ID.
    
    TODO: Implement with ytmusicapi.
    """
    logger.info(f"Get album: id='{album_id}'")
    return {"id": album_id, "title": f"Album {album_id}", "tracks": []}


@router.get("/playlist/{playlist_id}", response_model=PlaylistResponse, tags=["library"])
async def get_playlist(playlist_id: str):
    """
    Get playlist info by ID.
    
    TODO: Implement with ytmusicapi.
    """
    logger.info(f"Get playlist: id='{playlist_id}'")
    return PlaylistResponse(
        id=playlist_id,
        name=f"Playlist {playlist_id}",
        owner="local",
        is_youtube=False,
    )


# -----------------------------------------------------------------------------
# Queue Management
# -----------------------------------------------------------------------------

@router.post("/queue/select", tags=["queue"])
async def select_item(request: QueueSelectRequest):
    """
    Select an item (song, artist, album, playlist) to build the current queue.
    
    For now, creates a simple queue with mock data.
    """
    logger.info(f"Select item: type='{request.item_type}', id='{request.item_id}'")
    
    # TODO: Implement queue building logic
    # For now, create a mock queue
    db = next(get_userdb_session())
    
    import uuid
    # Create a new queue with a unique ID
    queue = Queue(
        id=f"mock_queue_{uuid.uuid4().hex[:8]}",
        name=f"Queue from {request.item_type} {request.item_id}",
        is_infinite=False,
    )
    db.add(queue)
    db.commit()
    db.refresh(queue)
    
    return {"message": "Queue created", "queue_id": queue.id}


@router.get("/queue", response_model=QueueResponse, tags=["queue"])
async def get_current_queue():
    """
    Get the current queue info.
    
    For now, returns mock data.
    """
    logger.info("Get current queue")
    
    # TODO: Get from playdb
    return QueueResponse(
        id="mock_queue_1",
        name="My Queue",
        is_infinite=False,
        songs=[
            SongResponse(
                id="dQw4w9WgXcQ",
                title="Rick Astley - Never Gonna Give You Up",
                artist="Rick Astley",
            ),
            SongResponse(
                id="9bZkp7q1984",
                title="Gorillaz - Feel Good Inc.",
                artist="Gorillaz",
            ),
        ]
    )


# -----------------------------------------------------------------------------
# Playback Control
# -----------------------------------------------------------------------------

@router.post("/queue/play", tags=["playback"])
async def play_queue():
    """Start playback of the current queue."""
    logger.info("Play queue")
    
    # TODO: Implement playback logic
    db = next(get_playdb_session())
    playback_state = db.query(PlaybackState).first()
    
    if not playback_state:
        playback_state = PlaybackState()
        db.add(playback_state)
    
    playback_state.is_playing = True
    db.commit()
    
    return {"message": "Playback started"}


@router.post("/queue/pause", tags=["playback"])
async def pause_queue():
    """Pause playback of the current queue."""
    logger.info("Pause queue")
    
    db = next(get_playdb_session())
    playback_state = db.query(PlaybackState).first()
    
    if playback_state:
        playback_state.is_playing = False
        db.commit()
    
    return {"message": "Playback paused"}


@router.post("/queue/next", tags=["playback"])
async def next_track():
    """Skip to next track in the queue."""
    logger.info("Next track")
    
    # TODO: Implement queue navigation
    return {"message": "Skipped to next track"}


@router.post("/queue/previous", tags=["playback"])
async def previous_track():
    """Go to previous track in the queue."""
    logger.info("Previous track")
    
    # TODO: Implement queue navigation
    return {"message": "Went to previous track"}


@router.post("/queue/seek", tags=["playback"])
async def seek(position_ms: int):
    """Seek to a specific position in the current track."""
    logger.info(f"Seek to: {position_ms}ms")
    
    db = next(get_playdb_session())
    playback_state = db.query(PlaybackState).first()
    
    if playback_state:
        playback_state.current_time_ms = position_ms
        db.commit()
    
    return {"message": f"Seeked to {position_ms}ms"}


@router.get("/playback/status", response_model=PlaybackStatusResponse, tags=["playback"])
async def get_playback_status():
    """
    Get current playback status.
    
    Returns:
    - Current queue ID
    - Current song ID and metadata
    - Playback position
    - Playback state (playing/paused)
    - Volume, repeat mode, shuffle
    """
    logger.info("Get playback status")
    
    db_play = next(get_playdb_session())
    playback_state = db_play.query(PlaybackState).first()
    
    db_user = next(get_userdb_session())
    current_song = None
    if playback_state and playback_state.current_song_id:
        song = db_user.query(Song).filter(Song.id == playback_state.current_song_id).first()
        if song:
            current_song = SongResponse(
                id=song.id,
                title=song.title,
                artist=song.artist,
                album=song.album,
                duration_ms=song.duration_ms,
                thumbnail_url=song.thumbnail_url,
            )
    
    return PlaybackStatusResponse(
        current_queue_id=playback_state.current_queue_id if playback_state else None,
        current_song_id=playback_state.current_song_id if playback_state else None,
        current_song=current_song,
        current_time_ms=playback_state.current_time_ms if playback_state else 0,
        is_playing=playback_state.is_playing if playback_state else False,
        volume=playback_state.volume if playback_state else 1.0,
        repeat_mode=playback_state.repeat_mode if playback_state else RepeatMode.NONE.value,
        shuffle=playback_state.shuffle if playback_state else False,
    )


@router.post("/playback/position", tags=["playback"])
async def update_playback_position(position_ms: int):
    """
    Update current playback position.
    
    Called by frontend every second during playback.
    """
    logger.debug(f"Update playback position: {position_ms}ms")
    
    db = next(get_playdb_session())
    playback_state = db.query(PlaybackState).first()
    
    if playback_state:
        playback_state.current_time_ms = position_ms
        playback_state.updated_at = datetime.utcnow()
        db.commit()
    
    return {"message": "Position updated"}
