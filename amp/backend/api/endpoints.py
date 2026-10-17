"""
FastAPI Endpoints
=================
REST API endpoints for AMP Backend.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from typing import Optional, List, Union, Dict
from pydantic import BaseModel
import io

from backend.utils.logger import get_logger
from backend.database.session import get_userdb_session, get_playdb_session
from backend.database.models import (
    Song,
    Playlist,
    Queue,
    QueueItem,
    PlaybackState,
    RepeatMode,
    CachedChunk,
)

# Import services
from backend.services.youtube import YouTubeService, get_youtube_service, SearchType
from backend.services.auth import AuthService, get_auth_service
from backend.services.streaming import StreamingService, get_streaming_service

router = APIRouter(tags=["api"])
logger = get_logger(__name__)

# Get service instances
youtube_service = get_youtube_service()
auth_service = get_auth_service()
streaming_service = get_streaming_service()


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


class AuthLoginRequest(BaseModel):
    """Request to initiate OAuth login."""
    redirect_uri: Optional[str] = None


class AuthCallbackRequest(BaseModel):
    """Request to handle OAuth callback."""
    code: str
    state: str
    redirect_uri: Optional[str] = None


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    # Check service health
    services_health = {
        "youtube_service": youtube_service is not None,
        "auth_service": auth_service is not None,
        "streaming_service": streaming_service is not None,
    }
    
    return {
        "status": "ok",
        "message": "AMP Backend is running",
        "services": services_health,
    }


# -----------------------------------------------------------------------------
# Authentication Endpoints
# -----------------------------------------------------------------------------

@router.post("/auth/login", tags=["auth"])
async def auth_login(request: AuthLoginRequest):
    """
    Initiate OAuth login flow.
    
    Returns:
    - auth_url: URL to redirect user to for authentication
    - state: State string for verification
    """
    logger.info("Initiating OAuth login")
    
    try:
        redirect_uri = request.redirect_uri or auth_service.REDIRECT_URI
        auth_url = auth_service.get_auth_url(redirect_uri=redirect_uri)
        
        if not auth_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to generate auth URL. Check OAuth configuration.",
            )
        
        logger.info(f"Generated OAuth URL: {auth_url[:50]}...")
        return {
            "auth_url": auth_url,
            "message": "Redirect user to this URL to authenticate",
        }
    except Exception as e:
        logger.error(f"Auth login failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate OAuth login: {str(e)}",
        )


@router.post("/auth/callback", tags=["auth"])
async def auth_callback(request: AuthCallbackRequest):
    """
    Handle OAuth callback.
    
    This endpoint receives the authorization code and exchanges it for tokens.
    """
    logger.info(f"Handling OAuth callback: state={request.state[:8]}...")

    redirect_uri = request.redirect_uri or auth_service.REDIRECT_URI

    try:
        success = auth_service.handle_oauth_callback(
            code=request.code,
            state=request.state,
            redirect_uri=redirect_uri,
        )
    except Exception as e:
        logger.exception("Auth callback failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to handle OAuth callback.",
        )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth callback failed. Invalid code or state.",
        )

    logger.info("OAuth callback handled successfully")
    return {"status": "authenticated", "message": "Authentication successful"}


@router.get("/auth/status", tags=["auth"])
async def auth_status():
    """
    Get current authentication status.
    
    Returns:
    - is_authenticated: Whether the user is authenticated
    - has_tokens: Whether authentication tokens are available
    - user_info: User information if authenticated
    """
    logger.info("Getting auth status")
    
    try:
        status = auth_service.get_auth_status()
        return status
    except Exception as e:
        logger.error(f"Failed to get auth status: {e}")
        return {
            "is_authenticated": False,
            "has_tokens": False,
            "error": str(e),
        }


@router.post("/auth/logout", tags=["auth"])
async def auth_logout():
    """Logout and clear authentication."""
    logger.info("Logging out")
    
    try:
        auth_service.logout()
        return {"status": "logged_out", "message": "Logged out successfully"}
    except Exception as e:
        logger.error(f"Failed to logout: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to logout: {str(e)}",
        )


@router.post("/auth/refresh", tags=["auth"])
async def auth_refresh():
    """Refresh authentication tokens."""
    logger.info("Refreshing tokens")
    
    try:
        success = auth_service.refresh_tokens()
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to refresh tokens",
            )
        
        return {"status": "refreshed", "message": "Tokens refreshed successfully"}
    except Exception as e:
        logger.error(f"Failed to refresh tokens: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh tokens: {str(e)}",
        )



@router.post("/auth/cookie-auth", tags=["auth"])
async def auth_cookie_auth():
    """
    Trigger browser-based cookie authentication via ytmusicapi.
    
    This opens a browser window for the user to log in to YouTube Music.
    After authentication, cookies are saved and used for API calls.
    
    This is the recommended auth method as it does not require Google Cloud credentials.
    """
    logger.info("Triggering cookie-based authentication")
    
    try:
        result = auth_service.trigger_cookie_auth()
        return result
    except Exception as e:
        logger.error(f"Cookie auth failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

# -----------------------------------------------------------------------------

@router.get("/search", response_model=List[SongResponse], tags=["library"])
async def search_songs(
    q: str = Query(..., description="Search query"),
    type: str = Query("all", description="Search type: all, song, artist, album, playlist"),
    limit: int = Query(20, description="Maximum results"),
):
    """
    Search YouTube Music library.
    
    Uses ytmusicapi to search for songs, artists, albums, and playlists.
    Results are cached in the local database.
    """
    logger.info(f"Search request: q='{q}', type='{type}', limit={limit}")
    
    try:
        # Convert type to SearchType enum (default to ALL if None or invalid)
        try:
            search_type = SearchType((type or "all").lower())
        except ValueError:
            search_type = SearchType.ALL
        
        # Perform search using YouTubeService
        search_result = youtube_service.search(
            query=q,
            search_type=search_type,
            limit=limit,
        )
        
        # Convert results to SongResponse
        responses = []
        for result in search_result.results:
            # Only include songs for now (can be extended for other types)
            if hasattr(result, 'id') and hasattr(result, 'title'):
                song_response = SongResponse(
                    id=result.id,
                    title=result.title,
                    artist=result.artist,
                    album=result.album if hasattr(result, 'album') else None,
                    duration_ms=result.duration_ms,
                    thumbnail_url=result.thumbnail_url,
                    year=result.year if hasattr(result, 'year') else None,
                    genre=result.genre if hasattr(result, 'genre') else None,
                )
                responses.append(song_response)
                
                # Cache the song in database
                _cache_song(song_response)
        
        logger.info(f"Search returned {len(responses)} results")
        
        # Fallback to mock data if no results
        if len(responses) == 0:
            logger.warning("No results from YouTube API, falling back to mock data")
            return _get_mock_search_results(q, limit)
        
        return responses
        
    except Exception as e:
        logger.error(f"Search failed: {e}")
        # Fallback to mock data if search fails
        logger.warning("Falling back to mock data")
        return _get_mock_search_results(q, limit)


def _cache_song(song: SongResponse) -> None:
    """Cache a song in the database."""
    try:
        db = next(get_userdb_session())
        
        # Check if song already exists
        existing = db.query(Song).filter(Song.id == song.id).first()
        
        if not existing:
            new_song = Song(
                id=song.id,
                title=song.title,
                artist=song.artist or "",
                album=song.album or "",
                duration_ms=song.duration_ms,
                thumbnail_url=song.thumbnail_url,
                year=song.year,
                genre=song.genre,
            )
            db.add(new_song)
            db.commit()
            logger.debug(f"Cached song: {song.title}")
        
    except Exception as e:
        logger.error(f"Failed to cache song: {e}")


@router.get("/song/{song_id}", response_model=SongResponse, tags=["library"])
async def get_song(song_id: str):
    """
    Get song metadata by ID.
    
    First checks local cache (userdb), then fetches from YouTube Music.
    """
    logger.info(f"Get song: id='{song_id}'")
    
    try:
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
        
        # Fetch from YouTube Music API
        song_metadata = youtube_service.get_song_metadata(song_id)
        
        if song_metadata:
            logger.info(f"Fetched song from YouTube: {song_metadata.title}")
            
            # Cache the song
            _cache_song(SongResponse(**song_metadata.to_dict()))
            
            return SongResponse(
                id=song_metadata.id,
                title=song_metadata.title,
                artist=song_metadata.artist,
                album=song_metadata.album,
                duration_ms=song_metadata.duration_ms,
                thumbnail_url=song_metadata.thumbnail_url,
                year=song_metadata.year,
                genre=song_metadata.genre,
            )
        else:
            logger.warning(f"Song not found in YouTube API: {song_id}, falling back to mock")
            # Fallback to mock data
            return SongResponse(
                id=song_id,
                title=f"Unknown Song ({song_id})",
                artist="Unknown Artist",
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get song: {e}")
        # Fallback to mock data
        return SongResponse(
            id=song_id,
            title=f"Unknown Song ({song_id})",
            artist="Unknown Artist",
        )


@router.get("/artist/{artist_id}", tags=["library"])
async def get_artist(artist_id: str):
    """
    Get artist info by ID.
    
    Fetches artist information from YouTube Music.
    """
    logger.info(f"Get artist: id='{artist_id}'")
    
    try:
        artist_info = youtube_service.get_artist_info(artist_id)
        
        if artist_info:
            logger.info(f"Fetched artist: {artist_info.name}")
            return {
                "id": artist_info.id,
                "name": artist_info.name,
                "thumbnail_url": artist_info.thumbnail_url,
                "description": artist_info.description,
                "subscriber_count": artist_info.subscriber_count,
                "top_tracks": artist_info.top_tracks,
                "related_artists": artist_info.related_artists,
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Artist not found: {artist_id}",
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get artist: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get artist: {str(e)}",
        )


@router.get("/album/{album_id}", tags=["library"])
async def get_album(album_id: str):
    """
    Get album info by ID.
    
    Fetches album information from YouTube Music.
    """
    logger.info(f"Get album: id='{album_id}'")
    
    try:
        album_info = youtube_service.get_album_info(album_id)
        
        if album_info:
            logger.info(f"Fetched album: {album_info.title}")
            return {
                "id": album_info.id,
                "title": album_info.title,
                "artist": album_info.artist,
                "artist_id": album_info.artist_id,
                "thumbnail_url": album_info.thumbnail_url,
                "year": album_info.year,
                "genre": album_info.genre,
                "track_count": album_info.track_count,
                "duration_ms": album_info.duration_ms,
                "explicit": album_info.explicit,
                "tracks": [_format_song_metadata(t) for t in (album_info.tracks or [])],
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Album not found: {album_id}",
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get album: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get album: {str(e)}",
        )
    
def _format_song_metadata(song) -> Dict:
    """Format song metadata for response."""
    return {
        "id": song.id,
        "title": song.title,
        "artist": song.artist,
        "duration_ms": song.duration_ms,
    }


@router.get("/playlist/{playlist_id}", response_model=PlaylistResponse, tags=["library"])
async def get_playlist(playlist_id: str):
    """
    Get playlist info by ID.
    
    Fetches playlist information from YouTube Music.
    """
    logger.info(f"Get playlist: id='{playlist_id}'")
    
    try:
        playlist_info = youtube_service.get_playlist_info(playlist_id)
        
        if playlist_info:
            logger.info(f"Fetched playlist: {playlist_info.name}")
            return PlaylistResponse(
                id=playlist_info.id,
                name=playlist_info.name,
                description=playlist_info.description,
                owner=playlist_info.owner or "",
                is_youtube=playlist_info.is_youtube,
                thumbnail_url=playlist_info.thumbnail_url,
                song_count=playlist_info.song_count or 0,
            )
        else:
            # Check if it's a local playlist
            db = next(get_userdb_session())
            playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
            
            if playlist:
                return PlaylistResponse(
                    id=playlist.id,
                    name=playlist.name,
                    description=playlist.description,
                    owner=playlist.owner,
                    is_youtube=False,
                    thumbnail_url=playlist.thumbnail_url,
                    song_count=playlist.song_count,
                )
            
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Playlist not found: {playlist_id}",
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get playlist: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get playlist: {str(e)}",
        )


# -----------------------------------------------------------------------------
# User Data Access (Requires Authentication)
# -----------------------------------------------------------------------------

@router.get("/user/playlists", tags=["user"])
async def get_user_playlists():
    """
    Get the user's playlists.
    
    Requires authentication.
    """
    logger.info("Getting user playlists")
    
    try:
        if not auth_service.is_authenticated:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        
        playlists = youtube_service.get_user_playlists()
        
        responses = []
        for playlist in playlists:
            responses.append(PlaylistResponse(
                id=playlist.id,
                name=playlist.name,
                description=playlist.description,
                owner="user",
                is_youtube=True,
                thumbnail_url=playlist.thumbnail_url,
                song_count=playlist.song_count or 0,
            ))
        
        return responses
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get user playlists: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user playlists: {str(e)}",
        )


@router.get("/user/likes", tags=["user"])
async def get_liked_songs():
    """
    Get the user's liked songs.
    
    Requires authentication.
    """
    logger.info("Getting liked songs")
    
    try:
        if not auth_service.is_authenticated:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        
        liked_songs = youtube_service.get_liked_songs()
        
        responses = []
        for song in liked_songs:
            responses.append(SongResponse(
                id=song.id,
                title=song.title,
                artist=song.artist,
                album=song.album,
                duration_ms=song.duration_ms,
                thumbnail_url=song.thumbnail_url,
                year=song.year,
                genre=song.genre,
            ))
        
        return responses
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get liked songs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get liked songs: {str(e)}",
        )


@router.post("/user/likes", tags=["user"])
async def like_song(song_id: str):
    """
    Like a song.
    
    Requires authentication.
    """
    logger.info(f"Liking song: {song_id}")
    
    try:
        if not auth_service.is_authenticated:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        
        # TODO: Implement like functionality via ytmusicapi
        # For now, just acknowledge
        logger.info(f"Song liked (not implemented): {song_id}")
        return {"status": "liked", "song_id": song_id, "message": "Song liked"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to like song: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to like song: {str(e)}",
        )


# -----------------------------------------------------------------------------
# Queue Management
# -----------------------------------------------------------------------------

@router.post("/queue/select", tags=["queue"])
async def select_item(request: QueueSelectRequest):
    """
    Select an item (song, artist, album, playlist) to build the current queue.
    """
    logger.info(f"Select item: type='{request.item_type}', id='{request.item_id}'")
    
    try:
        db = next(get_userdb_session())
        
        import uuid
        # Create a new queue with a unique ID
        queue = Queue(
            id=f"queue_{uuid.uuid4().hex[:8]}",
            name=f"Queue from {request.item_type} {request.item_id}",
            is_infinite=False,
        )
        db.add(queue)
        db.commit()
        db.refresh(queue)
        
        # Populate queue based on item type
        if request.item_type == "song":
            # Add single song to queue
            queue_item = QueueItem(
                queue_id=queue.id,
                song_id=request.item_id,
                position=0,
            )
            db.add(queue_item)
            db.commit()
        elif request.item_type == "artist":
            # Add artist's top tracks to queue
            artist_info = youtube_service.get_artist_info(request.item_id)
            if artist_info and artist_info.top_tracks:
                for idx, track in enumerate(artist_info.top_tracks):
                    queue_item = QueueItem(
                        queue_id=queue.id,
                        song_id=track.get("id"),
                        position=idx,
                    )
                    db.add(queue_item)
                db.commit()
        elif request.item_type == "album":
            # Add album tracks to queue
            album_info = youtube_service.get_album_info(request.item_id)
            if album_info and album_info.tracks:
                for idx, track in enumerate(album_info.tracks):
                    queue_item = QueueItem(
                        queue_id=queue.id,
                        song_id=track.id,
                        position=idx,
                    )
                    db.add(queue_item)
                db.commit()
        elif request.item_type == "playlist":
            # Add playlist tracks to queue
            playlist_info = youtube_service.get_playlist_info(request.item_id)
            if playlist_info and playlist_info.tracks:
                for idx, track in enumerate(playlist_info.tracks):
                    queue_item = QueueItem(
                        queue_id=queue.id,
                        song_id=track.id,
                        position=idx,
                    )
                    db.add(queue_item)
                db.commit()
        
        return {"message": "Queue created", "queue_id": queue.id}
        
    except Exception as e:
        logger.error(f"Failed to select item: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to select item: {str(e)}",
        )


@router.get("/queue", response_model=QueueResponse, tags=["queue"])
async def get_current_queue():
    """
    Get the current queue info.
    """
    logger.info("Get current queue")
    
    try:
        # For now, return the most recently created queue
        db = next(get_userdb_session())
        queue = db.query(Queue).order_by(Queue.created_at.desc()).first()
        
        if not queue:
            return QueueResponse(
                id="default",
                name="Default Queue",
                is_infinite=False,
                songs=[],
            )
        
        # Get queue items
        queue_items = db.query(
            QueueItem
        ).filter(QueueItem.queue_id == queue.id).order_by(QueueItem.position.asc()).all()
        
        # Get song metadata for each item
        songs = []
        for item in queue_items:
            song = db.query(Song).filter(Song.id == item.song_id).first()
            if song:
                songs.append(SongResponse(
                    id=song.id,
                    title=song.title,
                    artist=song.artist,
                    album=song.album,
                    duration_ms=song.duration_ms,
                    thumbnail_url=song.thumbnail_url,
                ))
            else:
                # Fetch from YouTube if not in cache
                song_metadata = youtube_service.get_song_metadata(item.song_id)
                if song_metadata:
                    songs.append(SongResponse(
                        id=song_metadata.id,
                        title=song_metadata.title,
                        artist=song_metadata.artist,
                        album=song_metadata.album,
                        duration_ms=song_metadata.duration_ms,
                        thumbnail_url=song_metadata.thumbnail_url,
                    ))
        
        return QueueResponse(
            id=queue.id,
            name=queue.name,
            is_infinite=queue.is_infinite,
            songs=songs,
        )
        
    except Exception as e:
        logger.error(f"Failed to get current queue: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get current queue: {str(e)}",
        )


# -----------------------------------------------------------------------------
# Playback Control
# -----------------------------------------------------------------------------

@router.post("/queue/play", tags=["playback"])
async def play_queue():
    """Start playback of the current queue."""
    logger.info("Play queue")
    
    try:
        db = next(get_playdb_session())
        playback_state = db.query(PlaybackState).first()
        
        if not playback_state:
            playback_state = PlaybackState()
            db.add(playback_state)
        
        playback_state.is_playing = True
        db.commit()
        
        return {"message": "Playback started"}
    except Exception as e:
        logger.error(f"Failed to play queue: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to play queue: {str(e)}",
        )


@router.post("/queue/pause", tags=["playback"])
async def pause_queue():
    """Pause playback of the current queue."""
    logger.info("Pause queue")
    
    try:
        db = next(get_playdb_session())
        playback_state = db.query(PlaybackState).first()
        
        if playback_state:
            playback_state.is_playing = False
            db.commit()
        
        return {"message": "Playback paused"}
    except Exception as e:
        logger.error(f"Failed to pause queue: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause queue: {str(e)}",
        )


@router.post("/queue/next", tags=["playback"])
async def next_track():
    """Skip to next track in the queue."""
    logger.info("Next track")
    
    try:
        # TODO: Implement queue navigation
        return {"message": "Skipped to next track"}
    except Exception as e:
        logger.error(f"Failed to skip to next track: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to skip to next track: {str(e)}",
        )


@router.post("/queue/previous", tags=["playback"])
async def previous_track():
    """Go to previous track in the queue."""
    logger.info("Previous track")
    
    try:
        # TODO: Implement queue navigation
        return {"message": "Went to previous track"}
    except Exception as e:
        logger.error(f"Failed to go to previous track: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to go to previous track: {str(e)}",
        )


@router.post("/queue/seek", tags=["playback"])
async def seek(position_ms: int):
    """Seek to a specific position in the current track."""
    logger.info(f"Seek to: {position_ms}ms")
    
    try:
        db = next(get_playdb_session())
        playback_state = db.query(PlaybackState).first()
        
        if playback_state:
            playback_state.current_time_ms = position_ms
            db.commit()
        
        return {"message": f"Seeked to {position_ms}ms"}
    except Exception as e:
        logger.error(f"Failed to seek: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to seek: {str(e)}",
        )


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
    
    try:
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
    except Exception as e:
        logger.error(f"Failed to get playback status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get playback status: {str(e)}",
        )


@router.post("/playback/position", tags=["playback"])
async def update_playback_position(position_ms: int):
    """
    Update current playback position.
    
    Called by frontend every second during playback.
    """
    logger.debug(f"Update playback position: {position_ms}ms")
    
    try:
        db = next(get_playdb_session())
        playback_state = db.query(PlaybackState).first()
        
        if playback_state:
            playback_state.current_time_ms = position_ms
            playback_state.updated_at = datetime.utcnow()
            db.commit()
        
        return {"message": "Position updated"}
    except Exception as e:
        logger.error(f"Failed to update playback position: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update playback position: {str(e)}",
        )


# -----------------------------------------------------------------------------
# Streaming Endpoints
# -----------------------------------------------------------------------------

@router.get("/stream/{song_id}", tags=["streaming"])
async def stream_song(song_id: str, chunk_index: int = 0):
    """
    Stream a specific chunk of a song.
    
    Args:
        song_id: YouTube video ID
        chunk_index: Chunk index to stream (0-based)
        
    Returns:
        StreamingResponse with audio data
    """
    logger.info(f"Stream request: song_id={song_id}, chunk_index={chunk_index}")
    
    try:
        # Get or download the chunk
        chunk_path = streaming_service.download_chunk(song_id, chunk_index)
        
        if not chunk_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chunk not available: {song_id} [{chunk_index}]",
            )
        
        # Stream the chunk file
        def iterfile():
            with open(chunk_path, "rb") as f:
                yield from f
        
        return StreamingResponse(
            iterfile(),
            media_type="audio/mpeg",
            headers={
                "Content-Length": str(os.path.getsize(chunk_path)),
                "Cache-Control": "no-cache",
            },
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stream: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stream: {str(e)}",
        )


@router.get("/stream/info/{song_id}", tags=["streaming"])
async def get_stream_info(song_id: str):
    """
    Get information about a stream.
    
    Args:
        song_id: YouTube video ID
        
    Returns:
        StreamInfo with chunk information
    """
    logger.info(f"Get stream info: song_id={song_id}")
    
    try:
        stream_info = streaming_service.get_stream_info(song_id)
        
        if not stream_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Stream info not available: {song_id}",
            )
        
        return {
            "song_id": stream_info.song_id,
            "title": stream_info.title,
            "duration_ms": stream_info.duration_ms,
            "mime_type": stream_info.mime_type,
            "chunk_size_ms": stream_info.chunk_size_ms,
            "total_chunks": stream_info.total_chunks,
            "cached_chunks": stream_info.cached_chunks,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get stream info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stream info: {str(e)}",
        )


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def _get_mock_search_results(query: str, limit: int) -> List[SongResponse]:
    """Return mock search results for fallback."""
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
