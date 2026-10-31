"""Unit tests for API endpoints — FastAPI TestClient.

Fully mocked, no network. Tests auth middleware, route ordering (P9),
health endpoint, and error handling.
"""

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Auth middleware (P17)
# ---------------------------------------------------------------------------


class TestAuthMiddleware:
    def test_health_no_auth_required(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_health_reports_extractor_prerequisites(self, client):
        extractor = client.get("/api/health").json()["services"]["extractor"]
        assert set(extractor) == {"node", "ejs", "yt_dlp"}
        assert isinstance(extractor["node"], bool)
        assert isinstance(extractor["ejs"], bool)

    def test_root_no_auth_required(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_missing_token_rejected(self, client):
        resp = client.get("/api/search?q=test")
        assert resp.status_code == 401

    def test_wrong_token_rejected(self, client):
        resp = client.get(
            "/api/search?q=test",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401

    def test_valid_token_accepted(self, client, auth_headers):
        # Search will fail (no network) but should not be 401
        resp = client.get("/api/search?q=test", headers=auth_headers)
        # 502 (search failed) or 200 — not 401
        assert resp.status_code != 401

    def test_options_exempt_from_auth(self, client):
        """CORS preflight (OPTIONS) must not require token."""
        resp = client.options(
            "/api/search",
            headers={
                "Origin": "http://localhost:1420",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Should not be 401
        assert resp.status_code != 401

    def test_invalid_song_id_rejected(self, client, auth_headers):
        """P13: invalid song_id should return 422 (path validation) or 400."""
        resp = client.get("/api/song/../../etc/passwd", headers=auth_headers)
        # FastAPI path param won't match the route, so 404 or 422
        assert resp.status_code in (400, 404, 422)


# ---------------------------------------------------------------------------
# Route ordering (P9)
# ---------------------------------------------------------------------------


class TestRouteOrdering:
    def test_playback_state_not_captured_by_song_id(self, client, auth_headers):
        """GET /api/stream/playback-state should hit the specific route, not /stream/{song_id}."""
        resp = client.get("/api/stream/playback-state", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "song_id" in data

    def test_stream_logs_not_captured_by_song_id(self, client, auth_headers):
        """GET /api/stream/logs should hit the specific route."""
        resp = client.get("/api/stream/logs", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "lines" in data


# ---------------------------------------------------------------------------
# Playback endpoints
# ---------------------------------------------------------------------------


class TestPlaybackEndpoints:
    def test_pause(self, client, auth_headers):
        resp = client.post("/api/stream/pause", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["message"] == "paused"

    def test_resume(self, client, auth_headers):
        resp = client.post("/api/stream/resume", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["message"] == "resumed"

    def test_stop(self, client, auth_headers):
        resp = client.post("/api/stream/stop", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["message"] == "stopped"

    def test_position_update(self, client, auth_headers):
        resp = client.post("/api/stream/position?position_ms=5000", headers=auth_headers)
        assert resp.status_code == 200

    def test_seek_no_active_song(self, client, auth_headers):
        resp = client.post("/api/stream/seek?position_ms=5000", headers=auth_headers)
        assert resp.status_code == 200
        # No active song — should return a message
        data = resp.json()
        assert "message" in data


# ---------------------------------------------------------------------------
# Log relay endpoints (P11)
# ---------------------------------------------------------------------------


class TestLogRelay:
    def test_post_and_get_logs(self, client, auth_headers):
        # Post some logs
        resp = client.post(
            "/api/logs",
            json={"lines": ["line 1", "line 2", "line 3"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200

        # Get them back
        resp = client.get("/api/logs", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "line 1" in data["lines"]
        assert "line 3" in data["lines"]

    def test_clear_logs(self, client, auth_headers):
        client.post("/api/logs", json={"lines": ["test"]}, headers=auth_headers)
        resp = client.delete("/api/logs", headers=auth_headers)
        assert resp.status_code == 200

        resp = client.get("/api/logs", headers=auth_headers)
        assert resp.json()["lines"] == []


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


class TestAuthEndpoints:
    def test_status_signed_out(self, client, auth_headers):
        resp = client.get("/api/auth/status", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "signed_out"
        assert data["is_authenticated"] is False

    def test_set_cookies(self, client, auth_headers):
        resp = client.post(
            "/api/auth/cookies",
            json={"cookie_header": "__Secure-3PAPISID=test123; HSID=abc"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "signed_in"

    def test_logout(self, client, auth_headers):
        # Set cookies first
        client.post(
            "/api/auth/cookies",
            json={"cookie_header": "__Secure-3PAPISID=test"},
            headers=auth_headers,
        )
        resp = client.post("/api/auth/logout", headers=auth_headers)
        assert resp.status_code == 200

        # Status should be signed_out
        resp = client.get("/api/auth/status", headers=auth_headers)
        assert resp.json()["state"] == "signed_out"

    def test_import_browser_keeps_only_youtube_cookies(self, client, auth_headers):
        """F12: browser import must not store other sites' cookies."""
        from types import SimpleNamespace
        from backend.services.auth import get_auth_service

        jar = [
            SimpleNamespace(name="__Secure-3PAPISID", value="yt", domain=".youtube.com"),
            SimpleNamespace(name="SID", value="google", domain=".google.com"),
            SimpleNamespace(name="session", value="secret", domain="bank.example"),
        ]
        with patch("yt_dlp.cookies.extract_cookies_from_browser", return_value=jar) as extract, \
             patch("yt_dlp.YoutubeDL") as ydl_cls:
            resp = client.post("/api/auth/import-browser?browser=chrome", headers=auth_headers)

        assert resp.status_code == 200
        assert resp.json()["state"] == "signed_in"
        extract.assert_called_once_with("chrome")
        ydl_cls.assert_not_called()  # no network extraction just to load cookies
        assert get_auth_service().get_cookies_dict() == {"__Secure-3PAPISID": "yt"}

    def test_import_browser_no_youtube_cookies(self, client, auth_headers):
        from types import SimpleNamespace

        jar = [SimpleNamespace(name="SID", value="google", domain=".google.com")]
        with patch("yt_dlp.cookies.extract_cookies_from_browser", return_value=jar):
            resp = client.post("/api/auth/import-browser?browser=chrome", headers=auth_headers)
        assert resp.status_code == 500
        assert "No cookies found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Song ID validation (P13)
# ---------------------------------------------------------------------------


class TestSongIdValidation:
    def test_valid_song_id_accepted(self, client, auth_headers):
        """Valid song ID should not be rejected by validation (may 502 on network)."""
        resp = client.get("/api/song/dQw4w9WgXcQ", headers=auth_headers)
        # 502 (network error) is fine — not a validation error
        assert resp.status_code in (200, 502)

    def test_invalid_song_id_play_endpoint(self, client, auth_headers):
        """Invalid song_id should be rejected with 422."""
        resp = client.post("/api/stream/../../etc/play", headers=auth_headers)
        # Path won't match route
        assert resp.status_code in (404, 422)


# ---------------------------------------------------------------------------
# Open mode (no token configured)
# ---------------------------------------------------------------------------


class TestOpenMode:
    """When no AUTH_TOKEN is configured, all endpoints are accessible without auth."""

    def test_health_no_auth(self, client_no_auth):
        resp = client_no_auth.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_root_no_auth(self, client_no_auth):
        resp = client_no_auth.get("/")
        assert resp.status_code == 200

    def test_search_no_token_accepted(self, client_no_auth):
        """Search should not return 401 in open mode (may 502 on network)."""
        resp = client_no_auth.get("/api/search?q=test")
        assert resp.status_code != 401

    def test_stream_endpoints_no_token(self, client_no_auth):
        """Streaming endpoints should not return 401 in open mode."""
        resp = client_no_auth.get("/api/stream/playback-state")
        assert resp.status_code == 200

        resp = client_no_auth.post("/api/stream/pause")
        assert resp.status_code == 200

        resp = client_no_auth.post("/api/stream/stop")
        assert resp.status_code == 200

    def test_auth_status_no_token(self, client_no_auth):
        resp = client_no_auth.get("/api/auth/status")
        assert resp.status_code == 200
        assert resp.json()["state"] == "signed_out"

    def test_user_likes_returns_401_when_signed_out(self, client_no_auth):
        """User-specific endpoints return 401 when not authenticated (cookies)."""
        resp = client_no_auth.get("/api/user/likes")
        assert resp.status_code == 401

    def test_user_playlists_returns_401_when_signed_out(self, client_no_auth):
        resp = client_no_auth.get("/api/user/playlists")
        assert resp.status_code == 401

    def test_logs_relay_no_token(self, client_no_auth):
        resp = client_no_auth.post("/api/logs", json={"lines": ["test"]})
        assert resp.status_code == 200
        resp = client_no_auth.get("/api/logs")
        assert resp.status_code == 200

    def test_host_header_still_validated(self, temp_dirs, monkeypatch):
        """Host check (DNS-rebinding guard) is always enforced, even in open mode."""
        from backend.config import settings
        monkeypatch.setattr(settings, "AUTH_TOKEN", None)
        from backend.api.server import create_app
        from fastapi.testclient import TestClient
        app = create_app(auth_token=None)
        # Use base_url with a bad host — httpx sets Host from the URL.
        # Must use a non-public path (health/root bypass the middleware).
        with TestClient(app, base_url="http://evil.com") as c:
            resp = c.get("/api/stream/playback-state")
            assert resp.status_code == 403

    def test_playback_state_no_token(self, client_no_auth):
        resp = client_no_auth.get("/api/stream/playback-state")
        assert resp.status_code == 200
        data = resp.json()
        assert "song_id" in data

    def test_seek_no_token(self, client_no_auth):
        resp = client_no_auth.post("/api/stream/seek?position_ms=5000")
        assert resp.status_code == 200

    def test_cache_info_no_token(self, client_no_auth):
        """GET /api/stream/cache-info should work in open mode."""
        resp = client_no_auth.get("/api/stream/cache-info")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_bytes" in data
        assert "total_mb" in data
        assert "max_mb" in data
        assert "usage_pct" in data
        assert "file_count" in data
        assert "song_count" in data

    def test_cache_info_with_token(self, client, auth_headers):
        """GET /api/stream/cache-info should work with token too."""
        resp = client.get("/api/stream/cache-info", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_bytes" in data
