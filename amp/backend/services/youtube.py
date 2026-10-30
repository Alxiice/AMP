"""YouTubeService — wraps ytmusicapi for search, metadata, likes, playlists.

Thread-safe singleton. Authenticated calls go through AuthService.client;
falls back to anonymous for search/metadata.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.services.auth import get_auth_service
from backend.utils.logger import get_logger

logger = get_logger("backend.services.youtube")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SongData:
    id: str
    title: str = ""
    artist: str = ""
    album: str = ""
    duration_ms: int = 0
    thumbnail_url: str = ""
    is_explicit: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration_ms": self.duration_ms,
            "thumbnail_url": self.thumbnail_url,
            "is_explicit": self.is_explicit,
        }


@dataclass
class PlaylistData:
    id: str
    name: str = ""
    owner: str = ""
    thumbnail_url: str = ""
    song_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "owner": self.owner,
            "thumbnail_url": self.thumbnail_url,
            "song_count": self.song_count,
        }


# ---------------------------------------------------------------------------
# Parsing helpers (ytmusicapi response -> dataclass)
# ---------------------------------------------------------------------------


def _parse_song(item: Dict[str, Any]) -> SongData:
    """Parse a ytmusicapi song/album-track dict into SongData."""
    video_id = item.get("videoId", "")
    title = item.get("title", "")

    artists = item.get("artists", [])
    artist_names = ", ".join(a.get("name", "") for a in artists if isinstance(a, dict))

    album_info = item.get("album")
    album_name = album_info.get("name", "") if isinstance(album_info, dict) else ""

    duration_ms = 0
    dur_text = item.get("duration", "")
    if dur_text and ":" in dur_text:
        parts = dur_text.split(":")
        try:
            if len(parts) == 2:
                duration_ms = (int(parts[0]) * 60 + int(parts[1])) * 1000
            elif len(parts) == 3:
                duration_ms = (int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])) * 1000
        except ValueError:
            pass
    elif item.get("duration_seconds"):
        duration_ms = int(item["duration_seconds"]) * 1000

    thumbnails = item.get("thumbnails", [])
    thumb = ""
    if thumbnails:
        thumb = max(thumbnails, key=lambda t: t.get("width", 0) * t.get("height", 0)).get("url", "")

    return SongData(
        id=video_id,
        title=title,
        artist=artist_names,
        album=album_name,
        duration_ms=duration_ms,
        thumbnail_url=thumb,
        is_explicit=item.get("isExplicit", False),
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class YouTubeService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._auth = get_auth_service()

    @property
    def _client(self) -> Any:
        return self._auth.get_client()

    # --- Search ---

    def search(self, query: str, search_type: str = "songs", limit: int = 20) -> List[Dict[str, Any]]:
        """Search YouTube Music. Works anonymously."""
        try:
            filter_map = {
                "songs": "songs",
                "videos": "videos",
                "albums": "albums",
                "artists": "artists",
                "playlists": "playlists",
            }
            stype = filter_map.get(search_type, "songs")
            results = self._client.search(query, filter=stype, limit=limit)
            if search_type in ("songs", "videos"):
                return [_parse_song(r).to_dict() for r in results if r.get("videoId")]
            return results
        except Exception as e:
            logger.error("Search failed for '%s': %s", query, e)
            raise

    # --- Metadata ---

    def get_song(self, song_id: str) -> Dict[str, Any]:
        try:
            info = self._client.get_song(song_id)
            return _parse_song(info.get("videoDetails", info)).to_dict()
        except Exception as e:
            logger.error("get_song failed for %s: %s", song_id, e)
            raise

    def get_artist(self, artist_id: str) -> Dict[str, Any]:
        try:
            return self._client.get_artist(artist_id)
        except Exception as e:
            logger.error("get_artist failed for %s: %s", artist_id, e)
            raise

    def get_album(self, album_id: str) -> Dict[str, Any]:
        try:
            return self._client.get_album(album_id)
        except Exception as e:
            logger.error("get_album failed for %s: %s", album_id, e)
            raise

    def get_playlist(self, playlist_id: str, limit: int = 100) -> Dict[str, Any]:
        try:
            return self._client.get_playlist(playlist_id, limit=limit)
        except Exception as e:
            logger.error("get_playlist failed for %s: %s", playlist_id, e)
            raise

    # --- Authenticated ---

    def get_liked_songs(self, limit: int = 100) -> List[Dict[str, Any]]:
        if not self._auth.is_authenticated:
            raise PermissionError("Not authenticated")
        try:
            results = self._client.get_liked_songs(limit=limit)
            return [_parse_song(r).to_dict() for r in results.get("tracks", []) if r.get("videoId")]
        except Exception as e:
            logger.error("get_liked_songs failed: %s", e)
            if "401" in str(e) or "403" in str(e):
                self._auth.mark_expired()
            raise

    def get_user_playlists(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not self._auth.is_authenticated:
            raise PermissionError("Not authenticated")
        try:
            results = self._client.get_library_playlists(limit=limit)
            return [
                PlaylistData(
                    id=p.get("playlistId", ""),
                    name=p.get("title", ""),
                    owner=p.get("author", {}).get("name", "") if isinstance(p.get("author"), dict) else "",
                    thumbnail_url=p.get("thumbnails", [{}])[-1].get("url", "") if p.get("thumbnails") else "",
                    song_count=p.get("count", 0),
                ).to_dict()
                for p in results
            ]
        except Exception as e:
            logger.error("get_user_playlists failed: %s", e)
            if "401" in str(e) or "403" in str(e):
                self._auth.mark_expired()
            raise


# --- Singleton ---

_instance: Optional[YouTubeService] = None
_lock = threading.Lock()


def get_youtube_service() -> YouTubeService:
    global _instance
    with _lock:
        if _instance is None:
            _instance = YouTubeService()
        return _instance


def reset_youtube_service() -> None:
    global _instance
    with _lock:
        _instance = None
