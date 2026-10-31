"""Main API endpoints: library (search, metadata, likes) + streaming + logs.

P9: Specific routes before parameterized ones.
P21: Blocking handlers are plain `def`.
"""

from __future__ import annotations

import threading
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.models import LikedSong, Song
from backend.database.session import get_db
from backend.services.streaming import get_streaming_service, validate_song_id
from backend.services.youtube import get_youtube_service
from backend.utils.logger import get_ring_lines

router = APIRouter(prefix="/api", tags=["api"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class SongResponse(BaseModel):
    id: str
    title: str = ""
    artist: str = ""
    album: str = ""
    duration_ms: int = 0
    thumbnail_url: str = ""
    is_explicit: bool = False


# ---------------------------------------------------------------------------
# Library endpoints
# ---------------------------------------------------------------------------


@router.get("/search", response_model=List[SongResponse])
def search(
    q: str = Query(..., min_length=1),
    type: str = Query("songs"),
    limit: int = Query(20, ge=1, le=50),
):
    """GET /api/search?q=&type=&limit="""
    yt = get_youtube_service()
    try:
        return yt.search(q, search_type=type, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Search failed: {e}")


@router.get("/song/{song_id}", response_model=SongResponse)
def get_song(song_id: str, db: Session = Depends(get_db)):
    """GET /api/song/{id} — check DB cache first, then YouTube."""
    validate_song_id(song_id)
    cached = db.get(Song, song_id)
    if cached:
        return SongResponse(
            id=cached.id, title=cached.title, artist=cached.artist,
            album=cached.album, duration_ms=cached.duration_ms,
            thumbnail_url=cached.thumbnail_url,
        )
    yt = get_youtube_service()
    try:
        data = yt.get_song(song_id)
        song = Song(
            id=data["id"], title=data["title"], artist=data["artist"],
            album=data["album"], duration_ms=data["duration_ms"],
            thumbnail_url=data["thumbnail_url"],
        )
        db.merge(song)
        db.commit()
        return SongResponse(**data)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch song: {e}")


@router.get("/artist/{artist_id}")
def get_artist(artist_id: str):
    """GET /api/artist/{id}"""
    yt = get_youtube_service()
    try:
        return yt.get_artist(artist_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch artist: {e}")


@router.get("/album/{album_id}")
def get_album(album_id: str):
    """GET /api/album/{id}"""
    yt = get_youtube_service()
    try:
        return yt.get_album(album_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch album: {e}")


@router.get("/playlist/{playlist_id}")
def get_playlist(playlist_id: str):
    """GET /api/playlist/{id}"""
    yt = get_youtube_service()
    try:
        return yt.get_playlist(playlist_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch playlist: {e}")


@router.get("/user/playlists")
def get_user_playlists():
    """GET /api/user/playlists (auth required)"""
    yt = get_youtube_service()
    try:
        return yt.get_user_playlists()
    except PermissionError:
        raise HTTPException(status_code=401, detail="Not authenticated")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed: {e}")


@router.get("/user/likes", response_model=List[SongResponse])
def get_user_likes(db: Session = Depends(get_db)):
    """GET /api/user/likes (auth required). Falls back to DB cache."""
    yt = get_youtube_service()
    try:
        results = yt.get_liked_songs()
        for data in results:
            song = Song(
                id=data["id"], title=data["title"], artist=data["artist"],
                album=data["album"], duration_ms=data["duration_ms"],
                thumbnail_url=data["thumbnail_url"],
            )
            db.merge(song)
            db.merge(LikedSong(song_id=data["id"]))
        db.commit()
        return results
    except PermissionError:
        raise HTTPException(status_code=401, detail="Not authenticated")
    except Exception as e:
        liked = db.query(LikedSong).join(Song).all()
        if liked:
            return [
                SongResponse(
                    id=row.song.id, title=row.song.title, artist=row.song.artist,
                    album=row.song.album, duration_ms=row.song.duration_ms,
                    thumbnail_url=row.song.thumbnail_url,
                )
                for row in liked
            ]
        raise HTTPException(status_code=502, detail=f"Failed to fetch likes: {e}")


# ---------------------------------------------------------------------------
# Streaming endpoints
# ---------------------------------------------------------------------------
# P9: Specific routes BEFORE parameterized ones.


@router.get("/stream/playback-state")
def get_playback_state():
    """GET /api/stream/playback-state"""
    return get_streaming_service().get_playback_state()


@router.get("/stream/logs")
def get_stream_logs(n: int = Query(200, ge=1, le=1000)):
    """GET /api/stream/logs — recent streaming log lines from ring buffer."""
    return {"lines": get_ring_lines(n)}


@router.get("/stream/cache-info")
def get_cache_info():
    """GET /api/stream/cache-info — cache statistics (size, usage, per-song)."""
    return get_streaming_service().get_cache_info()


@router.post("/stream/pause")
def pause():
    """POST /api/stream/pause"""
    return get_streaming_service().pause_playback()


@router.post("/stream/resume")
def resume():
    """POST /api/stream/resume"""
    return get_streaming_service().resume_playback()


@router.post("/stream/stop")
def stop():
    """POST /api/stream/stop"""
    return get_streaming_service().stop_playback()


@router.post("/stream/position")
def update_position(position_ms: int = Query(..., ge=0)):
    """POST /api/stream/position?position_ms="""
    return get_streaming_service().update_position(position_ms)


@router.post("/stream/seek")
def seek(position_ms: int = Query(..., ge=0)):
    """POST /api/stream/seek?position_ms="""
    return get_streaming_service().seek(position_ms)


# --- Parameterized song routes (must come after specific routes, P9) ---


@router.get("/stream/info/{song_id}")
def get_stream_info(song_id: str):
    """GET /api/stream/info/{id} — segment table summary."""
    validate_song_id(song_id)
    info = get_streaming_service().get_stream_info_summary(song_id)
    if not info:
        raise HTTPException(status_code=404, detail="Stream info not available")
    return info


@router.get("/stream/{song_id}/ready")
def is_stream_ready(song_id: str):
    """GET /api/stream/{id}/ready — check if stream info and initial segments are available."""
    validate_song_id(song_id)
    from backend.services.streaming import get_streaming_service, validate_song_id as _validate
    from pathlib import Path
    from backend.config import settings
    
    _validate(song_id)
    svc = get_streaming_service()
    info = svc.get_stream_info(song_id)  # Public method validates song_id
    if not info:
        return {"ready": False, "reason": "stream_info_not_available"}
    
    # Check if at least the init segment (if exists) and first segment are available
    def get_segment_file_path(song_id: str, index: int) -> Path:
        """Get the file path for a segment (replicates _segment_path logic)."""
        if index == -1:
            return settings.segments_dir / song_id / "init.bin"
        return settings.segments_dir / song_id / f"{index:04d}.bin"
    
    if info.has_init:
        init_path = get_segment_file_path(song_id, -1)
        if not init_path.exists():
            return {"ready": False, "reason": "init_segment_pending", "has_init": True}
    
    # Check if first segment is available
    if len(info.segments) > 0:
        first_seg_path = get_segment_file_path(song_id, 0)
        if not first_seg_path.exists():
            return {"ready": False, "reason": "first_segment_pending"}
    
    return {"ready": True, "mime_type": info.mime_type, "is_dash": info.is_dash}


@router.post("/stream/{song_id}/play")
def play_song(song_id: str):
    """POST /api/stream/{id}/play — start session + buffer."""
    validate_song_id(song_id)
    return get_streaming_service().start_playback(song_id)


@router.post("/stream/buffer/{song_id}")
def buffer_song(song_id: str):
    """POST /api/stream/buffer/{id} — force buffer-ahead."""
    validate_song_id(song_id)
    return get_streaming_service().buffer_ahead(song_id)


@router.get("/stream/{song_id}/chunks")
def get_chunks(song_id: str):
    """GET /api/stream/{id}/chunks — segment status list (for SegmentBar)."""
    validate_song_id(song_id)
    return {"segments": get_streaming_service().get_all_segment_statuses(song_id)}


@router.get("/stream/{song_id}/audio")
def get_audio(song_id: str, request: Request):
    """GET /api/stream/{id}/audio — binary with full Range support (§6.7, P16)."""
    validate_song_id(song_id)
    svc = get_streaming_service()

    range_header = request.headers.get("range")
    status, headers, body = svc.serve_audio_range(song_id, range_header)

    if status not in (200, 206):
        # JSON {detail, code}: segment_unavailable (502), extraction codes (404/401/502/503),
        # bad_range (416, keeps Content-Range). No header ever promises bytes we can't send (F7).
        extra = {"Content-Range": headers["Content-Range"]} if "Content-Range" in headers else None
        return JSONResponse(body, status_code=status, headers=extra)

    # A segment that fails mid-stream raises inside the generator: Starlette aborts
    # the connection instead of sending a body shorter than Content-Length.
    media_type = headers.get("Content-Type", "application/octet-stream")
    return StreamingResponse(body, status_code=status, headers=headers, media_type=media_type)


# ---------------------------------------------------------------------------
# Log relay endpoints (P11)
# ---------------------------------------------------------------------------

_log_relay: List[str] = []
_log_relay_lock = threading.Lock()


@router.get("/logs")
def get_logs(n: int = Query(500, ge=1, le=500)):
    """GET /api/logs — frontend log relay (last 500)."""
    with _log_relay_lock:
        return {"lines": _log_relay[-n:]}


@router.post("/logs")
def post_logs(body: dict):
    """POST /api/logs — accept frontend log lines."""
    lines = body.get("lines", [])
    with _log_relay_lock:
        _log_relay.extend(lines)
        del _log_relay[:-500]
    return {"message": "logged", "count": len(lines)}


@router.delete("/logs")
def delete_logs():
    """DELETE /api/logs — clear relay."""
    with _log_relay_lock:
        _log_relay.clear()
    return {"message": "cleared"}
