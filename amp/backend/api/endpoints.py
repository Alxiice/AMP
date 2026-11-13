"""Main API endpoints: library (search, metadata, likes) + streaming + logs.

P9: Specific routes before parameterized ones.
P21: Blocking handlers are plain `def`.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database.models import LikedSong, ListeningHistory, SavedQueue, Song
from backend.database.session import get_db
from backend.services.streaming import get_streaming_service, validate_song_id
from backend.services.youtube import get_youtube_service
from backend.utils.logger import get_logger, get_ring_lines

logger = get_logger("backend.api.endpoints")
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


@router.get("/song/{song_id}/album")
def get_song_album(song_id: str):
    """GET /api/song/{id}/album → {album_id} (null when the song has no album)."""
    validate_song_id(song_id)
    try:
        return {"album_id": get_youtube_service().get_song_album_id(song_id)}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to find the album: {e}")


@router.get("/song/{song_id}/loudness")
def get_song_loudness(song_id: str):
    """GET /api/song/{id}/loudness → {loudness_db}: YouTube's loudness for volume normalization.

    Best effort: null when YouTube doesn't report it or the lookup fails (the player then leaves the volume alone).
    """
    validate_song_id(song_id)
    try:
        return {"loudness_db": get_youtube_service().get_loudness_db(song_id)}
    except Exception as e:
        logger.warning("Loudness lookup failed for %s: %s", song_id, e)
        return {"loudness_db": None}


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
def get_playlist(playlist_id: str, limit: int = Query(1000, ge=1, le=5000)):
    """GET /api/playlist/{id} → {id, name, owner, thumbnail_url, song_count, songs}"""
    yt = get_youtube_service()
    try:
        return yt.get_playlist(playlist_id, limit=limit)
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


@router.post("/user/likes/{song_id}")
def like_song(song_id: str, song: Optional[SongResponse] = None, db: Session = Depends(get_db)):
    """POST /api/user/likes/{id} (auth required). The optional body fills the local cache."""
    validate_song_id(song_id)
    _rate(song_id, liked=True)
    if song and song.id == song_id:
        db.merge(Song(
            id=song.id, title=song.title, artist=song.artist, album=song.album,
            duration_ms=song.duration_ms, thumbnail_url=song.thumbnail_url,
        ))
        db.merge(LikedSong(song_id=song_id))
        db.commit()
    return {"song_id": song_id, "liked": True}


@router.delete("/user/likes/{song_id}")
def unlike_song(song_id: str, db: Session = Depends(get_db)):
    """DELETE /api/user/likes/{id} (auth required)."""
    validate_song_id(song_id)
    _rate(song_id, liked=False)
    row = db.get(LikedSong, song_id)
    if row:
        db.delete(row)
        db.commit()
    return {"song_id": song_id, "liked": False}


def _rate(song_id: str, liked: bool) -> None:
    try:
        get_youtube_service().rate_song(song_id, liked)
    except PermissionError:
        raise HTTPException(status_code=401, detail="Not authenticated")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to update like: {e}")


# ---------------------------------------------------------------------------
# Saved queues
# ---------------------------------------------------------------------------


class SavedQueueBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    songs: List[SongResponse] = Field(default_factory=list, max_length=5000)


class SavedQueueUpdate(BaseModel):
    """Only the fields that are set change."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    songs: Optional[List[SongResponse]] = Field(default=None, max_length=5000)


def _saved_queue_dict(row: SavedQueue, with_songs: bool = True) -> dict:
    songs = json.loads(row.songs_json)
    out = {
        "id": row.id,
        "name": row.name,
        "song_count": len(songs),
        "thumbnail_url": next((s["thumbnail_url"] for s in songs if s.get("thumbnail_url")), ""),
        "updated_at": row.updated_at.isoformat() + "Z",
    }
    if with_songs:
        out["songs"] = songs
    return out


def _dump_songs(songs: List[SongResponse]) -> str:
    for s in songs:
        validate_song_id(s.id)
    return json.dumps([s.model_dump() for s in songs])


def _get_saved_queue(db: Session, queue_id: int) -> SavedQueue:
    row = db.get(SavedQueue, queue_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Saved queue not found")
    return row


@router.get("/queues")
def list_saved_queues(db: Session = Depends(get_db)):
    """GET /api/queues — newest first, without the songs."""
    rows = db.query(SavedQueue).order_by(SavedQueue.updated_at.desc(), SavedQueue.id.desc()).all()
    return [_saved_queue_dict(r, with_songs=False) for r in rows]


@router.post("/queues", status_code=201)
def create_saved_queue(body: SavedQueueBody, db: Session = Depends(get_db)):
    """POST /api/queues {name, songs}"""
    row = SavedQueue(name=body.name.strip() or "Untitled queue", songs_json=_dump_songs(body.songs))
    db.add(row)
    db.commit()
    return _saved_queue_dict(row)


@router.get("/queues/{queue_id}")
def get_saved_queue(queue_id: int, db: Session = Depends(get_db)):
    return _saved_queue_dict(_get_saved_queue(db, queue_id))


@router.put("/queues/{queue_id}")
def update_saved_queue(queue_id: int, body: SavedQueueUpdate, db: Session = Depends(get_db)):
    """PUT /api/queues/{id} {name?, songs?} — rename and/or replace the songs."""
    row = _get_saved_queue(db, queue_id)
    if body.name is not None:
        row.name = body.name.strip() or row.name
    if body.songs is not None:
        row.songs_json = _dump_songs(body.songs)
    db.commit()
    return _saved_queue_dict(row)


@router.delete("/queues/{queue_id}")
def delete_saved_queue(queue_id: int, db: Session = Depends(get_db)):
    db.delete(_get_saved_queue(db, queue_id))
    db.commit()
    return {"message": "deleted"}


# ---------------------------------------------------------------------------
# Listening history
# ---------------------------------------------------------------------------


class HistoryBody(BaseModel):
    song: SongResponse
    listened_ms: int = Field(ge=0, le=24 * 3600 * 1000)
    duration_ms: int = Field(0, ge=0, le=24 * 3600 * 1000)
    started_at: Optional[dt.datetime] = None  # default: now - listened_ms
    end_reason: Literal["finished", "skipped", "stopped", "closed"] = "skipped"


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)  # stored naive UTC, like the other tables


def _naive_utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is not None:
        value = value.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return value


def _history_dict(row: ListeningHistory) -> dict:
    percent = min(100, round(row.listened_ms * 100 / row.duration_ms)) if row.duration_ms else None
    return {
        "id": row.id,
        "song": {"id": row.song_id, "title": row.title, "artist": row.artist, "album": row.album,
                 "duration_ms": row.duration_ms, "thumbnail_url": row.thumbnail_url, "is_explicit": False},
        "started_at": row.started_at.isoformat() + "Z",
        "listened_ms": row.listened_ms,
        "duration_ms": row.duration_ms,
        "percent": percent,
        "end_reason": row.end_reason,
    }


@router.post("/history", status_code=201)
def add_history(body: HistoryBody, db: Session = Depends(get_db)):
    """POST /api/history {song, listened_ms, duration_ms, started_at?, end_reason} — one play."""
    validate_song_id(body.song.id)
    now = _utc_now()
    started = _naive_utc(body.started_at) if body.started_at else now - dt.timedelta(milliseconds=body.listened_ms)
    row = ListeningHistory(
        song_id=body.song.id, title=body.song.title, artist=body.song.artist, album=body.song.album,
        thumbnail_url=body.song.thumbnail_url, duration_ms=body.duration_ms or body.song.duration_ms,
        listened_ms=body.listened_ms, started_at=min(started, now), end_reason=body.end_reason,
    )
    db.add(row)
    db.commit()
    return _history_dict(row)


@router.get("/history")
def list_history(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    days: int = Query(0, ge=0, le=3650, description="0 = all time"),
    db: Session = Depends(get_db),
):
    """GET /api/history — newest first: {entries, total, listened_ms}, totals over the period."""
    query = db.query(ListeningHistory)
    if days:
        query = query.filter(ListeningHistory.started_at >= _utc_now() - dt.timedelta(days=days))
    total = query.count()
    listened = query.with_entities(func.coalesce(func.sum(ListeningHistory.listened_ms), 0)).scalar()
    rows = (query.order_by(ListeningHistory.started_at.desc(), ListeningHistory.id.desc())
            .offset(offset).limit(limit).all())
    return {"entries": [_history_dict(r) for r in rows], "total": total, "listened_ms": int(listened)}


@router.delete("/history")
def clear_history(db: Session = Depends(get_db)):
    deleted = db.query(ListeningHistory).delete()
    db.commit()
    return {"message": "cleared", "deleted": deleted}


@router.delete("/history/{entry_id}")
def delete_history_entry(entry_id: int, db: Session = Depends(get_db)):
    row = db.get(ListeningHistory, entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="History entry not found")
    db.delete(row)
    db.commit()
    return {"message": "deleted"}


# ---------------------------------------------------------------------------
# Streaming endpoints
# ---------------------------------------------------------------------------
# P9: Specific routes BEFORE parameterized ones.


@router.get("/stream/playback-state")
def get_playback_state():
    """GET /api/stream/playback-state"""
    return get_streaming_service().get_playback_state()


@router.get("/stream/now-playing")
def get_now_playing():
    """GET /api/stream/now-playing — what the OBS widget shows ({song_id: null} when idle)."""
    return get_streaming_service().now_playing() or {"song_id": None}


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
    """GET /api/stream/info/{id} — segment table summary. Errors: api/errors.py."""
    validate_song_id(song_id)
    return get_streaming_service().get_stream_info_summary(song_id)


class NowPlayingMeta(BaseModel):
    """Shown by the OBS now-playing widget (backend/widget.py)."""
    title: str = Field("", max_length=500)
    artist: str = Field("", max_length=500)
    cover_url: str = Field("", max_length=2000)


@router.post("/stream/{song_id}/play")
def play_song(song_id: str, meta: Optional[NowPlayingMeta] = None):
    """POST /api/stream/{id}/play — resolve the stream, then start session + buffer.

    Blocks for the extraction on first play. 200 → {song_id, duration_ms,
    mime_type, segment_count, is_dash, epoch, cached_ahead}; errors use the
    {detail: {code, message}} shape (api/errors.py). Optional JSON body:
    {title, artist, cover_url} for the now-playing widget.
    """
    validate_song_id(song_id)
    return get_streaming_service().start_playback(song_id, meta.model_dump() if meta else None)


@router.post("/stream/buffer/{song_id}")
def buffer_song(song_id: str, mode: Literal["current", "prefetch"] = Query("current")):
    """POST /api/stream/buffer/{id}?mode= — current: buffer around the playhead;
    prefetch: resolve + init and 2 segments at LOW, session untouched."""
    validate_song_id(song_id)
    return get_streaming_service().buffer_ahead(song_id, mode)


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
