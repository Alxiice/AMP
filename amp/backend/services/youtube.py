"""
YouTube Service
==============
Service layer for YouTube Music API integration using ytmusicapi.

This service provides methods to:
- Search for songs, artists, albums, and playlists
- Get metadata for songs, artists, albums, and playlists
- Handle YouTube Music API authentication
"""

import os
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, asdict
from enum import Enum

from backend.config import (
    BASE_DIR,
    CACHE_DIR,
    YOUTUBE_API_KEY,
    YTMUSICAPI_COOKIES,
    DEBUG,
)
from backend.utils.logger import get_logger

logger = get_logger(__name__)


# Singleton instance
_youtube_service_instance = None


def get_youtube_service() -> "YouTubeService":
    """Get the singleton YouTubeService instance."""
    global _youtube_service_instance
    if _youtube_service_instance is None:
        _youtube_service_instance = YouTubeService()
    return _youtube_service_instance


class SearchType(str, Enum):
    """Types of items that can be searched."""
    ALL = "all"
    SONG = "song"
    ARTIST = "artist"
    ALBUM = "album"
    PLAYLIST = "playlist"


class SearchFilter(str, Enum):
    """Filters for search results."""
    SONGS = "songs"
    VIDEOS = "videos"
    ALBUMS = "albums"
    ARTISTS = "artists"
    PLAYLISTS = "playlists"
    FEATURED_PLAYLISTS = "featured_playlists"
    COMMUNITY_PLAYLISTS = "community_playlists"


@dataclass
class SongMetadata:
    """Song metadata from YouTube Music."""
    id: str
    title: str
    artist: Optional[str] = None
    artists: Optional[List[str]] = None
    album: Optional[str] = None
    album_id: Optional[str] = None
    duration_ms: Optional[int] = None
    thumbnail_url: Optional[str] = None
    year: Optional[int] = None
    genre: Optional[str] = None
    track_number: Optional[int] = None
    disc_number: Optional[int] = None
    explicit: Optional[bool] = None
    isrc: Optional[str] = None
    like_status: Optional[str] = None  # LIKED, DISLIKED, INDIFFERENT
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ArtistMetadata:
    """Artist metadata from YouTube Music."""
    id: str
    name: str
    thumbnail_url: Optional[str] = None
    description: Optional[str] = None
    subscriber_count: Optional[int] = None
    albums: Optional[List[Dict[str, Any]]] = None
    top_tracks: Optional[List[Dict[str, Any]]] = None
    related_artists: Optional[List[Dict[str, Any]]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class AlbumMetadata:
    """Album metadata from YouTube Music."""
    id: str
    title: str
    artist: Optional[str] = None
    artist_id: Optional[str] = None
    thumbnail_url: Optional[str] = None
    year: Optional[int] = None
    genre: Optional[str] = None
    track_count: Optional[int] = None
    duration_ms: Optional[int] = None
    explicit: Optional[bool] = None
    tracks: Optional[List[SongMetadata]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class PlaylistMetadata:
    """Playlist metadata from YouTube Music."""
    id: str
    name: str
    description: Optional[str] = None
    owner: Optional[str] = None
    owner_id: Optional[str] = None
    thumbnail_url: Optional[str] = None
    song_count: Optional[int] = None
    duration_ms: Optional[int] = None
    is_youtube: bool = True
    tracks: Optional[List[SongMetadata]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class SearchResult:
    """Search result container."""
    query: str
    search_type: str
    results: List[Union[SongMetadata, ArtistMetadata, AlbumMetadata, PlaylistMetadata]]
    total_results: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "query": self.query,
            "search_type": self.search_type,
            "results": [r.to_dict() for r in self.results],
            "total_results": self.total_results,
        }


class YouTubeService:
    """
    Service class for YouTube Music API integration.
    
    Uses ytmusicapi library to interact with YouTube Music.
    Handles authentication via cookies or OAuth.
    """
    
    def __init__(self):
        """Initialize the YouTubeService."""
        self._ytmusic = None
        self._is_authenticated = False
        self._cookies_file = self._get_cookies_file()
        self._authenticated_ytmusic = None
        self._initialize()
        # Automatically authenticate if cookies are available
        if self._cookies_file:
            self.authenticate()
    
    def _get_cookies_file(self) -> Optional[Path]:
        """Get the path to the cookies file."""
        if YTMUSICAPI_COOKIES:
            cookies_path = Path(YTMUSICAPI_COOKIES)
            if cookies_path.exists():
                return cookies_path
        
        # Default location
        default_cookies = CACHE_DIR / "cookies.json"
        if default_cookies.exists():
            return default_cookies
        
        return None
    
    def _initialize(self) -> None:
        """Initialize ytmusicapi."""
        try:
            import ytmusicapi as ytma
            self._ytmusic = ytma.YTMusic()
            logger.info("YouTubeService initialized (unauthenticated mode)")
            self._is_authenticated = False
        except ImportError as e:
            logger.error(f"ytmusicapi not installed: {e}")
            raise ImportError(
                "ytmusicapi is required for YouTube integration. "
                "Install it with: pip install ytmusicapi"
            )
        except Exception as e:
            logger.error(f"Failed to initialize ytmusicapi: {e}")
            raise
    
    def is_authenticated(self) -> bool:
        """Check if the service is authenticated."""
        return self._is_authenticated
    
    def authenticate(self, cookies_file: Optional[Path] = None) -> bool:
        """
        Authenticate with YouTube Music using cookies.
        
        Args:
            cookies_file: Path to cookies.json file. If None, uses the default.
            
        Returns:
            True if authentication succeeded, False otherwise.
        """
        try:
            import ytmusicapi as ytma
            
            if cookies_file:
                self._cookies_file = cookies_file
            
            if self._cookies_file and self._cookies_file.exists():
                logger.info(f"Authenticating with cookies: {self._cookies_file}")
                self._authenticated_ytmusic = ytma.YTMusic(
                    auth=str(self._cookies_file)
                )
                self._is_authenticated = True
                logger.info("YouTubeService authenticated successfully")
                return True
            else:
                logger.warning("No cookies file found for authentication")
                return False
                
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            self._is_authenticated = False
            self._authenticated_ytmusic = None
            return False
    
    def _get_ytmusic(self) -> Any:
        """Get the appropriate ytmusic instance (authenticated or unauthenticated)."""
        if self._is_authenticated and self._authenticated_ytmusic:
            return self._authenticated_ytmusic
        return self._ytmusic
    
    def get_auth_url(self) -> str:
        """
        Get the OAuth authentication URL.
        
        Returns:
            URL for OAuth authentication.
        """
        try:
            import ytmusicapi as ytma
            ytmusic = ytma.YTMusic()
            return ytmusic.get_auth_url()
        except Exception as e:
            logger.error(f"Failed to get auth URL: {e}")
            return ""
    
    def handle_oauth_callback(self, callback_data: Dict[str, str]) -> bool:
        """
        Handle OAuth callback and save cookies.
        
        Args:
            callback_data: Dictionary containing OAuth callback data.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            import ytmusicapi as ytma
            
            # Create a new YTMusic instance for OAuth
            ytmusic = ytma.YTMusic()
            
            # Handle the callback
            # Note: ytmusicapi's OAuth flow is a bit different
            # We need to use the oauth_credentials parameter
            if 'code' in callback_data:
                # This is a simplified flow
                # In practice, ytmusicapi uses a different OAuth approach
                # For now, we'll save the credentials to a file
                cookies_path = CACHE_DIR / "cookies.json"
                with open(cookies_path, 'w') as f:
                    json.dump(callback_data, f)
                
                self._cookies_file = cookies_path
                self._is_authenticated = True
                logger.info(f"OAuth cookies saved to: {cookies_path}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"OAuth callback failed: {e}")
            return False
    
    def search(
        self,
        query: str,
        search_type: SearchType = SearchType.ALL,
        filter: Optional[SearchFilter] = None,
        limit: int = 20,
        ignore_spelling: bool = False,
    ) -> SearchResult:
        """
        Search YouTube Music.
        
        Args:
            query: Search query string
            search_type: Type of search (all, song, artist, album, playlist)
            filter: Optional filter for results
            limit: Maximum number of results
            ignore_spelling: Whether to ignore spelling corrections
            
        Returns:
            SearchResult containing the results
        """
        logger.info(f"Searching: query='{query}', type={search_type.value}, limit={limit}")
        
        try:
            ytmusic = self._get_ytmusic()
            
            # Build search parameters (don't include query as it's passed separately)
            params = {
                "ignore_spelling": ignore_spelling,
            }
            
            # Add filter if specified
            if filter:
                params["filter"] = filter.value
            
            # Perform search based on type
            if search_type == SearchType.ALL:
                results = ytmusic.search(query, **params)
            elif search_type == SearchType.SONG:
                params["filter"] = SearchFilter.SONGS.value
                results = ytmusic.search(query, **params)
            elif search_type == SearchType.ARTIST:
                params["filter"] = SearchFilter.ARTISTS.value
                results = ytmusic.search(query, **params)
            elif search_type == SearchType.ALBUM:
                params["filter"] = SearchFilter.ALBUMS.value
                results = ytmusic.search(query, **params)
            elif search_type == SearchType.PLAYLIST:
                params["filter"] = SearchFilter.PLAYLISTS.value
                results = ytmusic.search(query, **params)
            else:
                results = ytmusic.search(query, **params)
            
            # Log raw results for debugging
            logger.debug(f"Raw search results type: {type(results)}, length: {len(results) if isinstance(results, list) else 'N/A'}")
            
            # Handle None results
            if results is None:
                logger.warning("ytmusic.search() returned None")
                results = []
            
            # Parse results
            parsed_results = self._parse_search_results(results, limit)
            
            return SearchResult(
                query=query,
                search_type=search_type.value,
                results=parsed_results,
                total_results=len(results) if isinstance(results, list) else 0,
            )
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            # Return empty results on error
            return SearchResult(
                query=query,
                search_type=search_type.value,
                results=[],
                total_results=0,
            )
    
    def _parse_search_results(
        self,
        results: List[Dict[str, Any]],
        limit: int,
    ) -> List[Union[SongMetadata, ArtistMetadata, AlbumMetadata, PlaylistMetadata]]:
        """Parse search results into metadata objects."""
        parsed = []
        
        # Ensure results is a list
        if not isinstance(results, list):
            logger.warning(f"Expected list of results, got {type(results)}")
            return parsed
        
        for item in results[:limit]:
            # Skip None or non-dict items
            if item is None or not isinstance(item, dict):
                continue
            category = item.get("category") or ""
            category = category.lower() if category else ""
            
            try:
                if category == "songs" or "videoId" in item:
                    song = self._parse_song(item)
                    if song:
                        parsed.append(song)
                elif category == "artists":
                    artist = self._parse_artist(item)
                    if artist:
                        parsed.append(artist)
                elif category == "albums":
                    album = self._parse_album(item)
                    if album:
                        parsed.append(album)
                elif category == "playlists":
                    playlist = self._parse_playlist(item)
                    if playlist:
                        parsed.append(playlist)
            except Exception as e:
                logger.debug(f"Failed to parse result item: {e}")
                continue
        
        return parsed
    
    def _parse_song(self, item: Dict[str, Any]) -> Optional[SongMetadata]:
        """Parse a song item from YouTube Music API response."""
        # Handle different result formats
        if "videoId" in item:
            video_id = item["videoId"]
        elif "id" in item:
            video_id = item["id"]
        else:
            return None
        
        # Extract title
        title = item.get("title") or item.get("name")
        if not title:
            return None
        
        # Extract artists
        artists = []
        artist_str = ""
        if "artists" in item:
            artists_raw = item["artists"]
            if isinstance(artists_raw, list):
                artists = [a.get("name", "") for a in artists_raw if isinstance(a, dict)]
                artist_str = ", ".join(artists)
            elif isinstance(artists_raw, str):
                artist_str = artists_raw
        
        # Extract album info
        album = None
        album_id = None
        if "album" in item and item["album"]:
            album_obj = item["album"]
            if isinstance(album_obj, dict):
                album = album_obj.get("name")
                album_id = album_obj.get("id")
            elif isinstance(album_obj, str):
                album = album_obj
        
        # Extract duration (convert from string to ms)
        duration_ms = None
        if "duration" in item:
            duration_str = item["duration"]
            if isinstance(duration_str, str):
                # Format: "PT4M20S" or "PT3M54S"
                try:
                    duration_ms = self._parse_duration(duration_str)
                except Exception:
                    pass
        elif "duration_ms" in item:
            duration_ms = item["duration_ms"]
        
        # Extract thumbnails
        thumbnail_url = None
        if "thumbnails" in item:
            thumbnails = item["thumbnails"]
            if isinstance(thumbnails, list) and len(thumbnails) > 0:
                thumbnail_url = thumbnails[-1].get("url")  # Use highest quality
        elif "thumbnail_url" in item:
            thumbnail_url = item["thumbnail_url"]
        
        # Extract year
        year = None
        if "year" in item:
            year = item["year"]
        
        return SongMetadata(
            id=video_id,
            title=title,
            artist=artist_str if artist_str else None,
            artists=artists if artists else None,
            album=album,
            album_id=album_id,
            duration_ms=duration_ms,
            thumbnail_url=thumbnail_url,
            year=year,
        )
    
    def _parse_duration(self, duration_str: str) -> int:
        """Parse ISO 8601 duration string to milliseconds."""
        # Format: PT#H#M#S or PT#M#S
        import re
        
        # Extract hours, minutes, seconds
        pattern = r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"
        match = re.match(pattern, duration_str)
        
        if match:
            hours = int(match.group(1)) if match.group(1) else 0
            minutes = int(match.group(2)) if match.group(2) else 0
            seconds = int(match.group(3)) if match.group(3) else 0
            
            return (hours * 3600 + minutes * 60 + seconds) * 1000
        
        return 0
    
    def _parse_artist(self, item: Dict[str, Any]) -> Optional[ArtistMetadata]:
        """Parse an artist item from YouTube Music API response."""
        artist_id = item.get("id") or item.get("channelId")
        if not artist_id:
            return None
        
        name = item.get("name")
        if not name:
            return None
        
        # Extract thumbnail
        thumbnail_url = None
        if "thumbnails" in item:
            thumbnails = item["thumbnails"]
            if isinstance(thumbnails, list) and len(thumbnails) > 0:
                thumbnail_url = thumbnails[-1].get("url")
        elif "thumbnail_url" in item:
            thumbnail_url = item["thumbnail_url"]
        
        return ArtistMetadata(
            id=artist_id,
            name=name,
            thumbnail_url=thumbnail_url,
        )
    
    def _parse_album(self, item: Dict[str, Any]) -> Optional[AlbumMetadata]:
        """Parse an album item from YouTube Music API response."""
        album_id = item.get("id") or item.get("browseId")
        if not album_id:
            return None
        
        title = item.get("title") or item.get("name")
        if not title:
            return None
        
        # Extract thumbnail
        thumbnail_url = None
        if "thumbnails" in item:
            thumbnails = item["thumbnails"]
            if isinstance(thumbnails, list) and len(thumbnails) > 0:
                thumbnail_url = thumbnails[-1].get("url")
        elif "thumbnail_url" in item:
            thumbnail_url = item["thumbnail_url"]
        
        # Extract artist
        artist = None
        artist_id = None
        if "artists" in item:
            artists_raw = item["artists"]
            if isinstance(artists_raw, list) and len(artists_raw) > 0:
                artist_obj = artists_raw[0]
                if isinstance(artist_obj, dict):
                    artist = artist_obj.get("name")
                    artist_id = artist_obj.get("id")
        
        # Extract year
        year = None
        if "year" in item:
            year = item["year"]
        
        # Extract track count
        track_count = None
        if "trackCount" in item:
            track_count = item["trackCount"]
        elif "song_count" in item:
            track_count = item["song_count"]
        
        return AlbumMetadata(
            id=album_id,
            title=title,
            artist=artist,
            artist_id=artist_id,
            thumbnail_url=thumbnail_url,
            year=year,
            track_count=track_count,
        )
    
    def _parse_playlist(self, item: Dict[str, Any]) -> Optional[PlaylistMetadata]:
        """Parse a playlist item from YouTube Music API response."""
        playlist_id = item.get("id") or item.get("playlistId")
        if not playlist_id:
            return None
        
        name = item.get("title") or item.get("name")
        if not name:
            return None
        
        # Extract thumbnail
        thumbnail_url = None
        if "thumbnails" in item:
            thumbnails = item["thumbnails"]
            if isinstance(thumbnails, list) and len(thumbnails) > 0:
                thumbnail_url = thumbnails[-1].get("url")
        elif "thumbnail_url" in item:
            thumbnail_url = item["thumbnail_url"]
        
        # Extract owner
        owner = None
        owner_id = None
        if "author" in item:
            author = item["author"]
            if isinstance(author, dict):
                owner = author.get("name")
                owner_id = author.get("id")
        
        # Extract song count
        song_count = None
        if "trackCount" in item:
            song_count = item["trackCount"]
        elif "song_count" in item:
            song_count = item["song_count"]
        
        return PlaylistMetadata(
            id=playlist_id,
            name=name,
            description=item.get("description"),
            owner=owner,
            owner_id=owner_id,
            thumbnail_url=thumbnail_url,
            song_count=song_count,
            is_youtube=True,
        )
    
    def get_song_metadata(self, song_id: str) -> Optional[SongMetadata]:
        """
        Get detailed metadata for a song.
        
        Args:
            song_id: YouTube video ID
            
        Returns:
            SongMetadata object or None if not found
        """
        logger.info(f"Getting song metadata: {song_id}")
        
        try:
            ytmusic = self._get_ytmusic()
            
            # Get song info
            song_info = ytmusic.get_song(song_id)
            
            if not song_info:
                logger.warning(f"Song not found: {song_id}")
                return None
            
            # Parse basic info
            video_id = song_info.get("videoId") or song_id
            title = song_info.get("title") or song_info.get("name")
            
            if not title:
                return None
            
            # Extract artists
            artists = []
            artist_str = ""
            if "artists" in song_info:
                artists_raw = song_info["artists"]
                if isinstance(artists_raw, list):
                    artists = [a.get("name", "") for a in artists_raw if isinstance(a, dict)]
                    artist_str = ", ".join(artists)
            
            # Extract album
            album = None
            album_id = None
            if "album" in song_info and song_info["album"]:
                album_obj = song_info["album"]
                if isinstance(album_obj, dict):
                    album = album_obj.get("name")
                    album_id = album_obj.get("id")
            
            # Extract duration
            duration_ms = None
            if "duration" in song_info:
                duration_str = song_info["duration"]
                if isinstance(duration_str, str):
                    duration_ms = self._parse_duration(duration_str)
            elif "duration_ms" in song_info:
                duration_ms = song_info["duration_ms"]
            
            # Extract thumbnails
            thumbnail_url = None
            if "thumbnails" in song_info:
                thumbnails = song_info["thumbnails"]
                if isinstance(thumbnails, list) and len(thumbnails) > 0:
                    thumbnail_url = thumbnails[-1].get("url")
            
            # Extract year
            year = song_info.get("year")
            
            # Extract other metadata
            genre = song_info.get("genre")
            track_number = song_info.get("trackNumber")
            disc_number = song_info.get("discNumber")
            explicit = song_info.get("explicit")
            isrc = song_info.get("isrc")
            like_status = song_info.get("likeStatus")
            
            return SongMetadata(
                id=video_id,
                title=title,
                artist=artist_str if artist_str else None,
                artists=artists if artists else None,
                album=album,
                album_id=album_id,
                duration_ms=duration_ms,
                thumbnail_url=thumbnail_url,
                year=year,
                genre=genre,
                track_number=track_number,
                disc_number=disc_number,
                explicit=explicit,
                isrc=isrc,
                like_status=like_status,
            )
            
        except Exception as e:
            logger.error(f"Failed to get song metadata: {e}")
            return None
    
    def get_artist_info(self, artist_id: str) -> Optional[ArtistMetadata]:
        """
        Get detailed information about an artist.
        
        Args:
            artist_id: YouTube channel ID
            
        Returns:
            ArtistMetadata object or None if not found
        """
        logger.info(f"Getting artist info: {artist_id}")
        
        try:
            ytmusic = self._get_ytmusic()
            
            # Get artist info
            artist_info = ytmusic.get_artist(artist_id)
            
            if not artist_info:
                logger.warning(f"Artist not found: {artist_id}")
                return None
            
            name = artist_info.get("name")
            if not name:
                return None
            
            # Extract thumbnail
            thumbnail_url = None
            if "thumbnails" in artist_info:
                thumbnails = artist_info["thumbnails"]
                if isinstance(thumbnails, list) and len(thumbnails) > 0:
                    thumbnail_url = thumbnails[-1].get("url")
            
            # Extract description
            description = artist_info.get("description")
            
            # Extract subscriber count
            subscriber_count = None
            if "subscriberCountText" in artist_info:
                try:
                    # Parse subscriber count text (e.g., "1.2M subscribers")
                    subscriber_text = artist_info["subscriberCountText"]
                    subscriber_count = self._parse_subscriber_count(subscriber_text)
                except Exception:
                    pass
            
            # Extract albums
            albums = []
            if "albums" in artist_info:
                albums_raw = artist_info["albums"]
                if isinstance(albums_raw, dict):
                    # Handle different album types
                    for album_type in ["singles", "albums", "compilations"]:
                        if album_type in albums_raw:
                            for album in albums_raw[album_type]:
                                albums.append({
                                    "id": album.get("id"),
                                    "title": album.get("title"),
                                    "year": album.get("year"),
                                    "thumbnail_url": album.get("thumbnails", [{}])[-1].get("url") if album.get("thumbnails") else None,
                                })
            
            # Extract top tracks
            top_tracks = []
            if "songs" in artist_info:
                for song in artist_info["songs"]:
                    top_tracks.append({
                        "id": song.get("videoId") or song.get("id"),
                        "title": song.get("title"),
                        "duration_ms": self._parse_duration(song.get("duration", "")) if song.get("duration") else None,
                    })
            
            # Extract related artists
            related_artists = []
            if "relatedArtists" in artist_info:
                for related in artist_info["relatedArtists"]:
                    related_artists.append({
                        "id": related.get("id") or related.get("channelId"),
                        "name": related.get("name"),
                    })
            
            return ArtistMetadata(
                id=artist_id,
                name=name,
                thumbnail_url=thumbnail_url,
                description=description,
                subscriber_count=subscriber_count,
                albums=albums if albums else None,
                top_tracks=top_tracks if top_tracks else None,
                related_artists=related_artists if related_artists else None,
            )
            
        except Exception as e:
            logger.error(f"Failed to get artist info: {e}")
            return None
    
    def _parse_subscriber_count(self, text: str) -> int:
        """Parse subscriber count text to integer."""
        import re
        
        # Extract number and unit (K, M, B)
        match = re.match(r"([\d.]+)\s*([KMGT]?)", text.replace(",", ""))
        
        if match:
            number = float(match.group(1))
            unit = match.group(2).upper()
            
            multipliers = {
                "": 1,
                "K": 1000,
                "M": 1000000,
                "B": 1000000000,
                "T": 1000000000000,
            }
            
            return int(number * multipliers.get(unit, 1))
        
        return 0
    
    def get_album_info(self, album_id: str) -> Optional[AlbumMetadata]:
        """
        Get detailed information about an album.
        
        Args:
            album_id: YouTube browse ID
            
        Returns:
            AlbumMetadata object or None if not found
        """
        logger.info(f"Getting album info: {album_id}")
        
        try:
            ytmusic = self._get_ytmusic()
            
            # Get album info
            album_info = ytmusic.get_album(album_id)
            
            if not album_info:
                logger.warning(f"Album not found: {album_id}")
                return None
            
            title = album_info.get("title") or album_info.get("name")
            if not title:
                return None
            
            # Extract thumbnail
            thumbnail_url = None
            if "thumbnails" in album_info:
                thumbnails = album_info["thumbnails"]
                if isinstance(thumbnails, list) and len(thumbnails) > 0:
                    thumbnail_url = thumbnails[-1].get("url")
            
            # Extract artist
            artist = None
            artist_id = None
            if "artists" in album_info:
                artists_raw = album_info["artists"]
                if isinstance(artists_raw, list) and len(artists_raw) > 0:
                    artist_obj = artists_raw[0]
                    if isinstance(artist_obj, dict):
                        artist = artist_obj.get("name")
                        artist_id = artist_obj.get("id")
            
            # Extract year
            year = album_info.get("year")
            
            # Extract genre
            genre = album_info.get("genre")
            
            # Extract track count and duration
            track_count = album_info.get("trackCount")
            duration_ms = album_info.get("duration_ms")
            if "duration" in album_info:
                duration_str = album_info["duration"]
                if isinstance(duration_str, str):
                    duration_ms = self._parse_duration(duration_str)
            
            # Extract explicit
            explicit = album_info.get("explicit")
            
            # Extract tracks
            tracks = []
            if "tracks" in album_info:
                for track in album_info["tracks"]:
                    track_metadata = self._parse_song(track)
                    if track_metadata:
                        tracks.append(track_metadata)
            
            return AlbumMetadata(
                id=album_id,
                title=title,
                artist=artist,
                artist_id=artist_id,
                thumbnail_url=thumbnail_url,
                year=year,
                genre=genre,
                track_count=track_count,
                duration_ms=duration_ms,
                explicit=explicit,
                tracks=tracks if tracks else None,
            )
            
        except Exception as e:
            logger.error(f"Failed to get album info: {e}")
            return None
    
    def get_playlist_info(self, playlist_id: str) -> Optional[PlaylistMetadata]:
        """
        Get detailed information about a playlist.
        
        Args:
            playlist_id: YouTube playlist ID
            
        Returns:
            PlaylistMetadata object or None if not found
        """
        logger.info(f"Getting playlist info: {playlist_id}")
        
        try:
            ytmusic = self._get_ytmusic()
            
            # Get playlist info
            playlist_info = ytmusic.get_playlist(playlist_id)
            
            if not playlist_info:
                logger.warning(f"Playlist not found: {playlist_id}")
                return None
            
            name = playlist_info.get("title") or playlist_info.get("name")
            if not name:
                return None
            
            # Extract thumbnail
            thumbnail_url = None
            if "thumbnails" in playlist_info:
                thumbnails = playlist_info["thumbnails"]
                if isinstance(thumbnails, list) and len(thumbnails) > 0:
                    thumbnail_url = thumbnails[-1].get("url")
            
            # Extract owner
            owner = None
            owner_id = None
            if "author" in playlist_info:
                author = playlist_info["author"]
                if isinstance(author, dict):
                    owner = author.get("name")
                    owner_id = author.get("id")
            
            # Extract description
            description = playlist_info.get("description")
            
            # Extract song count
            song_count = playlist_info.get("trackCount")
            
            # Extract duration
            duration_ms = None
            if "duration" in playlist_info:
                duration_str = playlist_info["duration"]
                if isinstance(duration_str, str):
                    duration_ms = self._parse_duration(duration_str)
            elif "duration_ms" in playlist_info:
                duration_ms = playlist_info["duration_ms"]
            
            # Extract tracks
            tracks = []
            if "tracks" in playlist_info:
                for track in playlist_info["tracks"]:
                    track_metadata = self._parse_song(track)
                    if track_metadata:
                        tracks.append(track_metadata)
            
            return PlaylistMetadata(
                id=playlist_id,
                name=name,
                description=description,
                owner=owner,
                owner_id=owner_id,
                thumbnail_url=thumbnail_url,
                song_count=song_count,
                duration_ms=duration_ms,
                is_youtube=True,
                tracks=tracks if tracks else None,
            )
            
        except Exception as e:
            logger.error(f"Failed to get playlist info: {e}")
            return None
    
    def get_user_playlists(self) -> List[PlaylistMetadata]:
        """
        Get the user's playlists.
        
        Requires authentication.
        
        Returns:
            List of PlaylistMetadata objects
        """
        if not self._is_authenticated:
            logger.warning("Cannot get user playlists: not authenticated")
            return []
        
        logger.info("Getting user playlists")
        
        try:
            ytmusic = self._get_ytmusic()
            
            # Get user playlists
            playlists_info = ytmusic.get_user_playlists()
            
            playlists = []
            for playlist in playlists_info:
                playlist_metadata = PlaylistMetadata(
                    id=playlist.get("id") or playlist.get("playlistId"),
                    name=playlist.get("title") or playlist.get("name"),
                    description=playlist.get("description"),
                    owner="user",
                    thumbnail_url=playlist.get("thumbnails", [{}])[-1].get("url") if playlist.get("thumbnails") else None,
                    song_count=playlist.get("trackCount"),
                    is_youtube=True,
                )
                playlists.append(playlist_metadata)
            
            return playlists
            
        except Exception as e:
            logger.error(f"Failed to get user playlists: {e}")
            return []
    
    def get_liked_songs(self) -> List[SongMetadata]:
        """
        Get the user's liked songs.
        
        Requires authentication.
        
        Returns:
            List of SongMetadata objects
        """
        if not self._is_authenticated:
            logger.warning("Cannot get liked songs: not authenticated")
            return []
        
        logger.info("Getting liked songs")
        
        try:
            ytmusic = self._get_ytmusic()
            
            # Get liked songs
            liked_songs_info = ytmusic.get_liked_songs()
            
            songs = []
            for song in liked_songs_info:
                song_metadata = self._parse_song(song)
                if song_metadata:
                    songs.append(song_metadata)
            
            return songs
            
        except Exception as e:
            logger.error(f"Failed to get liked songs: {e}")
            return []
    
    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about the authenticated user.
        
        Requires authentication.
        
        Returns:
            Dictionary with user information or None
        """
        if not self._is_authenticated:
            logger.warning("Cannot get user info: not authenticated")
            return None
        
        logger.info("Getting user info")
        
        try:
            ytmusic = self._get_ytmusic()
            
            # Get user info
            user_info = ytmusic.get_user()
            
            return user_info
            
        except Exception as e:
            logger.error(f"Failed to get user info: {e}")
            return None
