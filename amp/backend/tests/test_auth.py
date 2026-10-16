"""
Test Authentication Service
==========================
Unit and integration tests for authentication service.
"""
import pytest
import json
import os
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from datetime import datetime, timedelta

import sys

# Add backend to path
BACKEND_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(BACKEND_FOLDER))

from backend.services.auth import (
    AuthService,
    AuthToken,
    OAuthState,
    get_auth_service,
)
from backend.config import CACHE_DIR


class TestAuthServiceInitialization:
    """Tests for AuthService initialization."""
    
    def test_init_default(self):
        """Test default AuthService initialization."""
        service = AuthService()
        assert service is not None
        assert service._tokens is None
        assert service._is_authenticated == False
        assert service._user_info is None
    
    def test_init_loads_config(self):
        """Test that AuthService loads configuration."""
        with patch.dict(os.environ, {
            "YOUTUBE_CLIENT_ID": "test_client_id",
            "YOUTUBE_CLIENT_SECRET": "test_client_secret",
        }):
            service = AuthService()
            assert service.CLIENT_ID == "test_client_id"
            assert service.CLIENT_SECRET == "test_client_secret"


class TestAuthToken:
    """Tests for AuthToken dataclass."""
    
    def test_auth_token_creation(self):
        """Test creating an AuthToken."""
        token = AuthToken(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            token_type="Bearer",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        
        assert token.access_token == "test_access_token"
        assert token.refresh_token == "test_refresh_token"
        assert token.token_type == "Bearer"
        assert token.is_expired() == False
    
    def test_auth_token_expired(self):
        """Test checking if token is expired."""
        token = AuthToken(
            access_token="test",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        
        assert token.is_expired() == True
    
    def test_auth_token_to_dict(self):
        """Test converting AuthToken to dictionary."""
        token = AuthToken(
            access_token="test",
            refresh_token="refresh",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        
        data = token.to_dict()
        
        assert "access_token" in data
        assert "refresh_token" in data
        assert "expires_at" in data
        assert data["access_token"] == "test"
        assert data["refresh_token"] == "refresh"
    
    def test_auth_token_from_dict(self):
        """Test creating AuthToken from dictionary."""
        data = {
            "access_token": "test",
            "refresh_token": "refresh",
            "token_type": "Bearer",
            "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
        }
        
        token = AuthToken.from_dict(data)
        
        assert token.access_token == "test"
        assert token.refresh_token == "refresh"
        assert token.token_type == "Bearer"
        assert token.expires_at is not None


class TestOAuthState:
    """Tests for OAuthState dataclass."""
    
    def test_oauth_state_creation(self):
        """Test creating an OAuthState."""
        state = OAuthState(
            state="test_state",
            verifier="test_verifier",
            redirect_uri="http://localhost/callback",
            created_at=datetime.utcnow(),
            used=False,
        )
        
        assert state.state == "test_state"
        assert state.verifier == "test_verifier"
        assert state.redirect_uri == "http://localhost/callback"
        assert state.used == False
    
    def test_oauth_state_to_dict(self):
        """Test converting OAuthState to dictionary."""
        state = OAuthState(
            state="test",
            verifier="verifier",
            redirect_uri="http://localhost",
            created_at=datetime.utcnow(),
        )
        
        data = state.to_dict()
        
        assert "state" in data
        assert "verifier" in data
        assert "redirect_uri" in data
        assert "created_at" in data


class TestAuthServiceMethods:
    """Tests for AuthService methods."""
    
    @pytest.fixture
    def auth_service(self):
        """Create an AuthService instance."""
        service = AuthService()
        return service
    
    def test_get_auth_status(self, auth_service):
        """Test getting authentication status."""
        status = auth_service.get_auth_status()
        
        assert "is_authenticated" in status
        assert "has_tokens" in status
        assert status["is_authenticated"] == False
        assert status["has_tokens"] == False
    
    def test_is_authenticated(self, auth_service):
        """Test is_authenticated property."""
        assert auth_service.is_authenticated == False
    
    def test_assign_tokens(self, auth_service):
        """Test manually assigning tokens."""
        token = AuthToken(
            access_token="test",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        auth_service._tokens = token
        auth_service._is_authenticated = True
        
        assert auth_service.is_authenticated == True
        assert auth_service.tokens is not None
    
    def test_get_cookies_path(self):
        """Test getting cookies path."""
        # Create a test cookies file in the default location
        cookies_path = CACHE_DIR / "cookies.json"
        cookies_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Create a service instance
            from backend.services.auth import AuthService
            service = AuthService()
            
            # Save some dummy cookies
            service.save_cookies({}, path=cookies_path)
            
            # Now get_cookies_path should find it
            path = service.get_cookies_path()
            assert path == cookies_path
            
            # Cleanup
            if cookies_path.exists():
                cookies_path.unlink()
        finally:
            # Cleanup file
            if cookies_path.exists():
                cookies_path.unlink()
    
    def test_create_oauth_state(self, auth_service):
        """Test creating OAuth state."""
        state, code_challenge = auth_service.create_oauth_state(
            redirect_uri="http://localhost/callback"
        )
        
        assert state is not None
        assert code_challenge is not None
        assert len(state) > 0
        assert len(code_challenge) > 0
        
        # State should be stored
        oauth_state = auth_service.get_oauth_state(state)
        assert oauth_state is not None
    
    def test_get_oauth_state_not_found(self, auth_service):
        """Test getting non-existent OAuth state."""
        state = auth_service.get_oauth_state("nonexistent_state")
        assert state is None
    
    def test_mark_oauth_state_used(self, auth_service):
        """Test marking OAuth state as used."""
        state, _ = auth_service.create_oauth_state()
        
        auth_service.mark_oauth_state_used(state)
        
        # Get the state again
        oauth_state = auth_service.get_oauth_state(state)
        assert oauth_state.used == True


class TestAuthFlow:
    """Tests for OAuth authentication flow."""
    
    def test_get_auth_url(self):
        """Test generating auth URL."""
        service = AuthService()
        
        # Set client ID
        service.CLIENT_ID = "test_client_id"
        
        try:
            url = service.get_auth_url()
            
            assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth")
            assert "client_id=test_client_id" in url
            assert "response_type=code" in url
            assert "code_challenge" in url
            assert "code_challenge_method=S256" in url
        except ValueError:
            # Expected if no client ID
            pass
    
    def test_get_auth_url_no_client_id(self):
        """Test generating auth URL without client ID."""
        import os
        old_client_id = os.environ.get("YOUTUBE_CLIENT_ID")
        try:
            os.environ.pop("YOUTUBE_CLIENT_ID", None)
            service = AuthService()
            
            with pytest.raises(ValueError):
                service.get_auth_url()
        finally:
            if old_client_id:
                os.environ["YOUTUBE_CLIENT_ID"] = old_client_id
    
    def test_handle_oauth_callback(self):
        """Test handling OAuth callback."""
        service = AuthService()
        service.CLIENT_ID = "test_client_id"
        service.CLIENT_SECRET = "test_client_secret"
        
        # Create OAuth state
        state, verifier = service.create_oauth_state()
        
        # Mock requests
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "https://www.googleapis.com/auth/youtube.readonly",
            }
            mock_post.return_value = mock_response
            
            # Handle callback
            success = service.handle_oauth_callback(
                code="test_code",
                state=state,
                redirect_uri="http://localhost/callback",
            )
            
            assert success == True
            assert service.is_authenticated == True
            assert service.tokens is not None
            
            # Clean up: remove token file to prevent test pollution
            token_file = CACHE_DIR / "auth_tokens.json"
            if token_file.exists():
                token_file.unlink()
    
    def test_handle_oauth_callback_invalid_state(self):
        """Test handling OAuth callback with invalid state."""
        # Clear any existing OAuth sessions
        from backend.services.auth import _oauth_sessions
        _oauth_sessions.clear()
        
        # Clear any existing token file to ensure clean state
        token_file = CACHE_DIR / "auth_tokens.json"
        if token_file.exists():
            token_file.unlink()
        
        # Create a fresh service instance
        service = AuthService()
        
        success = service.handle_oauth_callback(
            code="test_code",
            state="invalid_state",
        )
        
        assert success == False
        assert service.is_authenticated == False


class TestTokenManagement:
    """Tests for token management."""
    
    @pytest.fixture
    def auth_service_with_tokens(self):
        """Create AuthService with tokens."""
        service = AuthService()
        
        # Create a token file
        token_file = CACHE_DIR / "auth_tokens.json"
        token_file.parent.mkdir(parents=True, exist_ok=True)
        
        token_data = {
            "access_token": "test_token",
            "refresh_token": "test_refresh",
            "token_type": "Bearer",
            "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
        }
        
        with open(token_file, 'w') as f:
            json.dump(token_data, f)
        
        return service
    
    def test_load_tokens_from_file(self, auth_service_with_tokens):
        """Test loading tokens from file."""
        # The service should load tokens on initialization
        # But we need to force a reload
        token_file = CACHE_DIR / "auth_tokens.json"
        
        try:
            # Manually call _load_tokens
            auth_service_with_tokens._load_tokens()
            
            # Check if tokens were loaded
            assert auth_service_with_tokens._tokens is not None
            assert auth_service_with_tokens._tokens.access_token == "test_token"
            
            # Cleanup
            if token_file.exists():
                token_file.unlink()
        except Exception:
            # Cleanup
            if token_file.exists():
                token_file.unlink()
            raise
    
    def test_save_tokens_to_file(self):
        """Test saving tokens to file."""
        service = AuthService()
        
        # Assign tokens
        service._tokens = AuthToken(
            access_token="test_save_token",
            refresh_token="test_save_refresh",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        
        token_file = service.TOKEN_FILE
        
        try:
            service._save_tokens()
            
            assert token_file.exists()
            
            with open(token_file, 'r') as f:
                saved_data = json.load(f)
            
            assert saved_data["access_token"] == "test_save_token"
            assert saved_data["refresh_token"] == "test_save_refresh"
            
            # Cleanup
            if token_file.exists():
                token_file.unlink()
        except Exception:
            # Cleanup
            if token_file.exists():
                token_file.unlink()
            raise
    
    def test_clear_tokens(self):
        """Test clearing tokens."""
        service = AuthService()
        
        # Assign tokens
        service._tokens = AuthToken(
            access_token="test",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        service._is_authenticated = True
        
        token_file = service.TOKEN_FILE
        
        try:
            service._clear_tokens()
            
            assert service._tokens is None
            assert service._is_authenticated == False
            
            # Token file should be deleted
            assert not token_file.exists()
        finally:
            # Cleanup
            if token_file.exists():
                token_file.unlink()


class TestCookieManagement:
    """Tests for cookie management."""
    
    def test_save_cookies(self):
        """Test saving cookies to file."""
        service = AuthService()
        
        cookies = {
            "test_cookie": "test_value",
        }
        
        cookies_path = CACHE_DIR / "test_cookies_management.json"
        
        try:
            success = service.save_cookies(cookies, path=cookies_path)
            
            assert success == True
            assert cookies_path.exists()
            
            with open(cookies_path, 'r') as f:
                saved_cookies = json.load(f)
            
            assert saved_cookies["test_cookie"] == "test_value"
            
            # Cleanup
            cookies_path.unlink()
        except Exception:
            # Cleanup
            if cookies_path.exists():
                cookies_path.unlink()
            raise
    
    def test_load_cookies(self):
        """Test loading cookies from file."""
        service = AuthService()
        
        cookies_path = CACHE_DIR / "test_cookies_load.json"
        
        cookies = {
            "test_cookie": "test_value",
        }
        
        try:
            # Save cookies first
            with open(cookies_path, 'w') as f:
                json.dump(cookies, f)
            
            # Load cookies
            loaded_cookies = service.load_cookies(path=cookies_path)
            
            assert loaded_cookies is not None
            assert loaded_cookies["test_cookie"] == "test_value"
            
            # Cleanup
            cookies_path.unlink()
        except Exception:
            # Cleanup
            if cookies_path.exists():
                cookies_path.unlink()
            raise
    
    def test_load_cookies_not_found(self):
        """Test loading cookies from non-existent file."""
        service = AuthService()
        
        cookies = service.load_cookies(path=CACHE_DIR / "nonexistent.json")
        
        assert cookies is None


class TestLogout:
    """Tests for logout functionality."""
    
    def test_logout(self):
        """Test logging out."""
        service = AuthService()
        
        # Set authenticated state
        service._is_authenticated = True
        service._tokens = AuthToken(
            access_token="test",
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        
        token_file = service.TOKEN_FILE
        
        try:
            service.logout()
            
            assert service.is_authenticated == False
            assert service._tokens is None
            assert service._user_info is None
            
            # Token file should be deleted
            assert not token_file.exists()
        finally:
            # Cleanup
            if token_file.exists():
                token_file.unlink()


class TestCodeChallenge:
    """Tests for PKCE code challenge generation."""
    
    def test_generate_code_challenge(self):
        """Test generating PKCE code challenge."""
        service = AuthService()
        
        verifier = "test_verifier_string"
        challenge = service._generate_code_challenge(verifier)
        
        # Challenge should be a base64 URL-safe string
        assert challenge is not None
        assert len(challenge) > 0
        
        # Challenge should be different from verifier
        assert challenge != verifier
    
    def test_code_challenge_consistency(self):
        """Test that same verifier produces same challenge."""
        service = AuthService()
        
        verifier = "test_verifier"
        challenge1 = service._generate_code_challenge(verifier)
        challenge2 = service._generate_code_challenge(verifier)
        
        assert challenge1 == challenge2
    
    def test_code_challenge_different_verifiers(self):
        """Test that different verifiers produce different challenges."""
        service = AuthService()
        
        challenge1 = service._generate_code_challenge("verifier1")
        challenge2 = service._generate_code_challenge("verifier2")
        
        assert challenge1 != challenge2


class TestSingletonService:
    """Tests for singleton service access."""
    
    def test_get_auth_service_singleton(self):
        """Test that get_auth_service returns the same instance."""
        service1 = get_auth_service()
        service2 = get_auth_service()
        
        assert service1 is service2
