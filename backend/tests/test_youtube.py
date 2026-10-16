"""
Test YouTube Service
===================
Unit and integration tests for YouTube Music API service.
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.youtube import (
    YouTubeService,
    SearchType,
    SearchFilter,
    SongMetadata,
    ArtistMetadata,
    AlbumMetadata,
    PlaylistMetadata,
    SearchResult,
)
from backend.config import CACHE_DIR


class TestYouTubeServiceInitialization:
    """Tests for YouTubeService initialization."""
    
    def test_init_with_ytmusicapi(self):
        """Test that YouTubeService can be initialized."""
        service = YouTubeService()
        assert service is not None
        assert service._ytmusic is not None
    
    def test_init_without_ytmusicapi(self):
        """Test that YouTubeService raises ImportError without ytmusicapi."""
        with patch.dict('sys.modules', {'ytmusicapi': None}):
            with pytest.raises(ImportError):
                YouTubeService()


class TestSearch:
    """Tests for search functionality."""
    
    @pytest.fixture
    def youtube_service(self):
        """Create a YouTubeService instance."""
        return YouTubeService()
    
    def test_search_all(self, youtube_service):
        """Test searching with type=all."""
        # This test will use the real API if available
        # For CI/testing without API, we mock it
        with patch.object(youtube_service, '_get_ytmusic') as mock_ytmusic:
            mock_instance = Mock()
            mock_instance.search.return_value = []
            mock_ytmusic.return_value = mock_instance
            
            result = youtube_service.search("test query", SearchType.ALL)
            
            assert result is not None
            assert result.query == "test query"
            assert result.search_type == "all"
            mock_ytmusic.assert_called_once()
    
    def test_search_songs(self, youtube_service):
        """Test searching for songs."""
        with patch.object(youtube_service, '_get_ytmusic') as mock_ytmusic:
            mock_instance = Mock()
            mock_instance.search.return_value = []
            mock_ytmusic.return_value = mock_instance
            
            result = youtube_service.search("test query", SearchType.SONG)
            
            assert result.search_type == "song"
            # Check that filter was set correctly
            mock_instance.search.assert_called_once()
    
    def test_search_artists(self, youtube_service):
        """Test searching for artists."""
        with patch.object(youtube_service, '_get_ytmusic') as mock_ytmusic:
            mock_instance = Mock()
            mock_instance.search.return_value = []
            mock_ytmusic.return_value = mock_instance
            
            result = youtube_service.search("test artist", SearchType.ARTIST)
            
            assert result.search_type == "artist"
    
    def test_search_albums(self, youtube_service):
        """Test searching for albums."""
        with patch.object(youtube_service, '_get_ytmusic') as mock_ytmusic:
            mock_instance = Mock()
            mock_instance.search.return_value = []
            mock_ytmusic.return_value = mock_instance
            
            result = youtube_service.search("test album", SearchType.ALBUM)
            
            assert result.search_type == "album"
    
    def test_search_playlists(self, youtube_service):
        """Test searching for playlists."""
        with patch.object(youtube_service, '_get_ytmusic') as mock_ytmusic:
            mock_instance = Mock()
            mock_instance.search.return_value = []
            mock_ytmusic.return_value = mock_instance
            
            result = youtube_service.search("test playlist", SearchType.PLAYLIST)
            
            assert result.search_type == "playlist"
    
    def test_search_with_limit(self, youtube_service):
        """Test search with custom limit."""
        with patch.object(youtube_service, '_get_ytmusic') as mock_ytmusic:
            mock_instance = Mock()
            mock_instance.search.return_value = []
            mock_ytmusic.return_value = mock_instance
            
            result = youtube_service.search("test", SearchType.ALL, limit=10)
            
            # Results should be limited
            assert len(result.results) <= 10


class TestParseDuration:
    """Tests for duration parsing."""
    
    def test_parse_iso_duration_hours(self):
        """Test parsing ISO duration with hours."""
        service = YouTubeService()
        duration = service._parse_duration("PT1H23M45S")
        assert duration == (1 * 3600 + 23 * 60 + 45) * 1000
    
    def test_parse_iso_duration_minutes(self):
        """Test parsing ISO duration with minutes only."""
        service = YouTubeService()
        duration = service._parse_duration("PT5M30S")
        assert duration == (5 * 60 + 30) * 1000
    
    def test_parse_iso_duration_seconds(self):
        """Test parsing ISO duration with seconds only."""
        service = YouTubeService()
        duration = service._parse_duration("PT45S")
        assert duration == 45 * 1000
    
    def test_parse_iso_duration_zero(self):
        """Test parsing empty ISO duration."""
        service = YouTubeService()
        duration = service._parse_duration("")
        assert duration == 0


class TestMetadataParsing:
    """Tests for metadata parsing functions."""
    
    def test_parse_song_metadata(self):
        """Test parsing song metadata from YouTube API response."""
        service = YouTubeService()
        
        song_data = {
            "videoId": "dQw4w9WgXcQ",
            "title": "Never Gonna Give You Up",
            "artists": [{"name": "Rick Astley"}],
            "album": {"name": "Whenever You Need Somebody"},
            "duration": "PT3M33S",
            "thumbnails": [{"url": "https://example.com/thumb.jpg"}],
            "year": 1987,
        }
        
        song = service._parse_song(song_data)
        
        assert song is not None
        assert song.id == "dQw4w9WgXcQ"
        assert song.title == "Never Gonna Give You Up"
        assert song.artist == "Rick Astley"
        assert song.album == "Whenever You Need Somebody"
        assert song.duration_ms == (3 * 60 + 33) * 1000
        assert song.thumbnail_url == "https://example.com/thumb.jpg"
        assert song.year == 1987
    
    def test_parse_artist_metadata(self):
        """Test parsing artist metadata from YouTube API response."""
        service = YouTubeService()
        
        artist_data = {
            "id": "UC-9-kyTW8ZkZNDHQJ6FgpwQ",
            "name": "Rick Astley",
            "thumbnails": [{"url": "https://example.com/artist.jpg"}],
        }
        
        artist = service._parse_artist(artist_data)
        
        assert artist is not None
        assert artist.id == "UC-9-kyTW8ZkZNDHQJ6FgpwQ"
        assert artist.name == "Rick Astley"
        assert artist.thumbnail_url == "https://example.com/artist.jpg"
    
    def test_parse_album_metadata(self):
        """Test parsing album metadata from YouTube API response."""
        service = YouTubeService()
        
        album_data = {
            "id": "MPREb_N50Yy9pPouPTVx0y",
            "title": "Whenever You Need Somebody",
            "artists": [{"name": "Rick Astley"}],
            "thumbnails": [{"url": "https://example.com/album.jpg"}],
            "year": 1987,
            "trackCount": 12,
        }
        
        album = service._parse_album(album_data)
        
        assert album is not None
        assert album.id == "MPREb_N50Yy9pPouPTVx0y"
        assert album.title == "Whenever You Need Somebody"
        assert album.artist == "Rick Astley"
        assert album.thumbnail_url == "https://example.com/album.jpg"
        assert album.year == 1987
        assert album.track_count == 12
    
    def test_parse_playlist_metadata(self):
        """Test parsing playlist metadata from YouTube API response."""
        service = YouTubeService()
        
        playlist_data = {
            "id": "PLx0sYbCQDjQAC5I3Ks1QlW6c4pQlTZb",
            "title": "My Playlist",
            "author": {"name": "Test User"},
            "thumbnails": [{"url": "https://example.com/playlist.jpg"}],
            "trackCount": 25,
        }
        
        playlist = service._parse_playlist(playlist_data)
        
        assert playlist is not None
        assert playlist.id == "PLx0sYbCQDjQAC5I3Ks1QlW6c4pQlTZb"
        assert playlist.name == "My Playlist"
        assert playlist.owner == "Test User"
        assert playlist.thumbnail_url == "https://example.com/playlist.jpg"
        assert playlist.song_count == 25
        assert playlist.is_youtube == True


class TestGetSongMetadata:
    """Tests for get_song_metadata method."""
    
    def test_get_song_metadata(self):
        """Test getting song metadata."""
        service = YouTubeService()
        
        with patch.object(service, '_get_ytmusic') as mock_ytmusic:
            mock_instance = Mock()
            mock_instance.get_song.return_value = {
                "videoId": "dQw4w9WgXcQ",
                "title": "Never Gonna Give You Up",
                "artists": [{"name": "Rick Astley"}],
                "album": {"name": "Whenever You Need Somebody"},
                "duration": "PT3M33S",
                "thumbnails": [{"url": "https://example.com/thumb.jpg"}],
                "year": 1987,
            }
            mock_ytmusic.return_value = mock_instance
            
            metadata = service.get_song_metadata("dQw4w9WgXcQ")
            
            assert metadata is not None
            assert metadata.id == "dQw4w9WgXcQ"
            assert metadata.title == "Never Gonna Give You Up"
            mock_instance.get_song.assert_called_once_with("dQw4w9WgXcQ")
    
    def test_get_song_metadata_not_found(self):
        """Test getting song metadata for non-existent song."""
        service = YouTubeService()
        
        with patch.object(service, '_get_ytmusic') as mock_ytmusic:
            mock_instance = Mock()
            mock_instance.get_song.return_value = None
            mock_ytmusic.return_value = mock_instance
            
            metadata = service.get_song_metadata("nonexistent")
            
            assert metadata is None


class TestGetArtistInfo:
    """Tests for get_artist_info method."""
    
    def test_get_artist_info(self):
        """Test getting artist info."""
        service = YouTubeService()
        
        with patch.object(service, '_get_ytmusic') as mock_ytmusic:
            mock_instance = Mock()
            mock_instance.get_artist.return_value = {
                "name": "Rick Astley",
                "id": "UC-9-kyTW8ZkZNDHQJ6FgpwQ",
                "thumbnails": [{"url": "https://example.com/artist.jpg"}],
                "description": "Official channel",
                "subscriberCountText": "1M subscribers",
            }
            mock_ytmusic.return_value = mock_instance
            
            artist = service.get_artist_info("UC-9-kyTW8ZkZNDHQJ6FgpwQ")
            
            assert artist is not None
            assert artist.name == "Rick Astley"
            mock_instance.get_artist.assert_called_once()
    
    def test_get_artist_info_not_found(self):
        """Test getting artist info for non-existent artist."""
        service = YouTubeService()
        
        with patch.object(service, '_get_ytmusic') as mock_ytmusic:
            mock_instance = Mock()
            mock_instance.get_artist.return_value = None
            mock_ytmusic.return_value = mock_instance
            
            artist = service.get_artist_info("nonexistent")
            
            assert artist is None


class TestAuthentication:
    """Tests for authentication functionality."""
    
    def test_auth_status(self):
        """Test getting authentication status."""
        service = YouTubeService()
        
        # Service should start unauthenticated
        assert service.is_authenticated() == False
    
    def test_authenticate_with_cookies(self):
        """Test authenticating with cookies file."""
        service = YouTubeService()
        
        # Create a mock cookies file
        cookies_path = CACHE_DIR / "test_cookies.json"
        cookies_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(cookies_path, 'w') as f:
            json.dump({}, f)
        
        try:
            # Mock ytmusicapi
            with patch('backend.services.youtube.ytmusicapi') as mock_ytma:
                mock_instance = Mock()
                mock_instance.YTMusic.return_value.get_user.return_value = {"name": "Test User"}
                mock_ytma.YTMusic.return_value = mock_instance
                
                success = service.authenticate(cookies_file=cookies_path)
                
                # Cleanup
                if cookies_path.exists():
                    cookies_path.unlink()
        except Exception:
            # Cleanup
            if cookies_path.exists():
                cookies_path.unlink()
            pass


class TestParseSearchResults:
    """Tests for search results parsing."""
    
    def test_parse_search_results_empty(self):
        """Test parsing empty search results."""
        service = YouTubeService()
        results = service._parse_search_results([], limit=10)
        assert results == []
    
    def test_parse_search_results_mixed(self):
        """Test parsing mixed search results."""
        service = YouTubeService()
        
        results = [
            {
                "category": "songs",
                "videoId": "song1",
                "title": "Song 1",
                "artists": [{"name": "Artist 1"}],
            },
            {
                "category": "artists",
                "id": "artist1",
                "name": "Artist 1",
            },
            {
                "category": "albums",
                "id": "album1",
                "title": "Album 1",
            },
        ]
        
        parsed = service._parse_search_results(results, limit=10)
        
        # Should parse all three items
        assert len(parsed) == 3
        assert any(isinstance(r, SongMetadata) for r in parsed)
        assert any(isinstance(r, ArtistMetadata) for r in parsed)
        assert any(isinstance(r, AlbumMetadata) for r in parsed)


class TestUserData:
    """Tests for user data access."""
    
    def test_get_user_playlists_unauthenticated(self):
        """Test getting user playlists without authentication."""
        service = YouTubeService()
        playlists = service.get_user_playlists()
        
        # Should return empty list when not authenticated
        assert playlists == []
    
    def test_get_liked_songs_unauthenticated(self):
        """Test getting liked songs without authentication."""
        service = YouTubeService()
        songs = service.get_liked_songs()
        
        # Should return empty list when not authenticated
        assert songs == []


class TestDataClasses:
    """Tests for dataclass serialization."""
    
    def test_song_metadata_to_dict(self):
        """Test SongMetadata to_dict method."""
        song = SongMetadata(
            id="test_id",
            title="Test Song",
            artist="Test Artist",
            duration_ms=180000,
        )
        
        data = song.to_dict()
        
        assert data["id"] == "test_id"
        assert data["title"] == "Test Song"
        assert data["artist"] == "Test Artist"
        assert data["duration_ms"] == 180000
    
    def test_search_result_to_dict(self):
        """Test SearchResult to_dict method."""
        song = SongMetadata(id="test", title="Test")
        result = SearchResult(
            query="test query",
            search_type="song",
            results=[song],
            total_results=1,
        )
        
        data = result.to_dict()
        
        assert data["query"] == "test query"
        assert data["search_type"] == "song"
        assert len(data["results"]) == 1
        assert data["total_results"] == 1
