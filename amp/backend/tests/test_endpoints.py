"""
Test API Endpoints
==================
Integration tests for FastAPI endpoints.
"""
import pytest
from fastapi.testclient import TestClient

from backend.api.server import app


@pytest.fixture(scope="module")
def client():
    """Create a test client for the FastAPI app."""
    with TestClient(app) as c:
        yield c


class TestHealthEndpoint:
    """Tests for health check endpoint."""
    
    def test_health_check(self, client):
        """Test health check returns OK."""
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestSearchEndpoint:
    """Tests for search endpoint."""
    
    def test_search_songs(self, client):
        """Test searching for songs."""
        response = client.get("/api/search?q=rick+astley&type=all")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        
        # Check first result has required fields
        first_song = data[0]
        assert "id" in first_song
        assert "title" in first_song


class TestSongEndpoint:
    """Tests for song endpoint."""
    
    def test_get_song_not_in_cache(self, client):
        """Test getting a song not in cache."""
        response = client.get("/api/song/dQw4w9WgXcQ")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "dQw4w9WgXcQ"
        assert "title" in data


class TestQueueEndpoints:
    """Tests for queue endpoints."""
    
    def test_select_item(self, client):
        """Test selecting an item for the queue."""
        response = client.post("/api/queue/select", json={
            "item_type": "song",
            "item_id": "dQw4w9WgXcQ"
        })
        assert response.status_code == 200
        data = response.json()
        assert "queue_id" in data

    def test_get_current_queue(self, client):
        """Test getting current queue."""
        response = client.get("/api/queue")
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "songs" in data


class TestPlaybackEndpoints:
    """Tests for playback endpoints."""
    
    def test_play_queue(self, client):
        """Test starting playback."""
        response = client.post("/api/queue/play")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_pause_queue(self, client):
        """Test pausing playback."""
        response = client.post("/api/queue/pause")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_next_track(self, client):
        """Test skipping to next track."""
        response = client.post("/api/queue/next")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_previous_track(self, client):
        """Test going to previous track."""
        response = client.post("/api/queue/previous")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_seek(self, client):
        """Test seeking in current track."""
        response = client.post("/api/queue/seek?position_ms=50000")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_get_playback_status(self, client):
        """Test getting playback status."""
        response = client.get("/api/playback/status")
        assert response.status_code == 200
        data = response.json()
        assert "is_playing" in data
        assert "current_time_ms" in data
        assert "volume" in data
        assert "repeat_mode" in data
        assert "shuffle" in data

    def test_update_playback_position(self, client):
        """Test updating playback position."""
        response = client.post("/api/playback/position?position_ms=15000")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data


class TestAuthEndpoints:
    """Tests for authentication endpoints."""
    
    def test_auth_login_endpoint(self, client):
        """Test POST /auth/login returns auth_url with default redirect_uri."""
        response = client.post("/api/auth/login", json={})
        assert response.status_code == 200
        data = response.json()
        assert "auth_url" in data
        assert "https://accounts.google.com/o/oauth2" in data["auth_url"]
        # Should use default redirect_uri from config
        assert "redirect_uri=" in data["auth_url"]
    
    def test_auth_login_endpoint_custom_redirect(self, client):
        """Test POST /auth/login with custom redirect_uri."""
        custom_uri = "http://custom:8080/callback"
        response = client.post("/api/auth/login", json={"redirect_uri": custom_uri})
        assert response.status_code == 200
        data = response.json()
        assert "auth_url" in data
        assert custom_uri in data["auth_url"]
    
    def test_auth_status_endpoint(self, client):
        """Test GET /auth/status returns status."""
        response = client.get("/api/auth/status")
        assert response.status_code == 200
        data = response.json()
        assert "is_authenticated" in data
        assert "has_tokens" in data
        assert data["is_authenticated"] == False
    
    def test_auth_logout_endpoint(self, client):
        """Test POST /auth/logout returns success."""
        response = client.post("/api/auth/logout")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "logged_out"
    
    def test_auth_callback_endpoint_invalid_state(self, client):
        """Test POST /auth/callback with invalid state returns 400."""
        response = client.post("/api/auth/callback", json={
            "code": "test_code",
            "state": "invalid_state"
        })
        assert response.status_code == 400
        data = response.json()
        assert "Invalid code or state" in data["detail"]
