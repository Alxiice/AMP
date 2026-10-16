"""
Authentication Service
====================
Service layer for YouTube Music authentication and OAuth flow.

This service provides:
- OAuth flow handling
- Token storage and management
- Authentication state management
"""

import os
import json
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import secrets
import hashlib

from backend.config import (
    BASE_DIR,
    CACHE_DIR,
    YOUTUBE_API_KEY,
    YTMUSICAPI_COOKIES,
    YOUTUBE_REDIRECT_URI,
    YOUTUBE_REDIRECT_URI,
    YOUTUBE_REDIRECT_URI,
    DEBUG,
)
from backend.utils.logger import get_logger

logger = get_logger(__name__)


# Session storage for OAuth flows
_oauth_sessions: Dict[str, Dict[str, Any]] = {}


# Singleton instance
_auth_service_instance = None


def get_auth_service() -> "AuthService":
    """Get the singleton AuthService instance."""
    global _auth_service_instance
    if _auth_service_instance is None:
        _auth_service_instance = AuthService()
    return _auth_service_instance


@dataclass
class OAuthState:
    """Represents an OAuth session state."""
    state: str
    verifier: str
    redirect_uri: str
    created_at: datetime
    used: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        # Convert datetime to ISO string
        if isinstance(data.get("created_at"), datetime):
            data["created_at"] = self.created_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OAuthState":
        """Create from dictionary."""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except (ValueError, TypeError):
                # Handle naive datetime strings (without timezone)
                created_at = datetime.fromisoformat(created_at)
        elif isinstance(created_at, datetime):
            pass  # Already a datetime
        else:
            created_at = datetime.utcnow()
        
        return cls(
            state=data.get("state"),
            verifier=data.get("verifier"),
            redirect_uri=data.get("redirect_uri"),
            created_at=created_at,
            used=data.get("used", False),
        )


@dataclass
class AuthToken:
    """Represents authentication tokens."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_at: Optional[datetime] = None
    scopes: Optional[list] = None
    
    def is_expired(self) -> bool:
        """Check if token is expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() >= self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        if self.expires_at:
            data["expires_at"] = self.expires_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuthToken":
        """Create from dictionary."""
        expires_at = None
        if "expires_at" in data and data["expires_at"]:
            try:
                # Try parsing as ISO format
                expires_at = datetime.fromisoformat(data["expires_at"])
            except (ValueError, TypeError, AttributeError):
                # If it fails, leave as None or try other formats
                pass
        return cls(
            access_token=data.get("access_token"),
            refresh_token=data.get("refresh_token"),
            token_type=data.get("token_type", "Bearer"),
            expires_at=expires_at,
            scopes=data.get("scopes"),
        )


class AuthService:
    """
    Service class for handling YouTube Music authentication.
    
    Provides OAuth flow, token storage, and authentication state management.
    """
    
    # Token storage file
    TOKEN_FILE = CACHE_DIR / "auth_tokens.json"
    
    # OAuth configuration
    OAUTH_SCOPES = [
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]
    
    # Client ID and secret (can be configured via environment)
    CLIENT_ID: Optional[str] = None
    CLIENT_SECRET: Optional[str] = None
    REDIRECT_URI: Optional[str] = None
    REDIRECT_URI: Optional[str] = None
    REDIRECT_URI: Optional[str] = None
    
    def __init__(self):
        """Initialize the AuthService."""
        self._tokens: Optional[AuthToken] = None
        self._is_authenticated: bool = False
        self._user_info: Optional[Dict[str, Any]] = None
        self._session_id: Optional[str] = None
        
        # Load configuration
        self._load_config()
        
        # Load saved tokens
        self._load_tokens()
        
        # Ensure directories exist
        os.makedirs(CACHE_DIR, exist_ok=True)
    
    def _load_config(self) -> None:
        """Load OAuth configuration from environment or config."""
        # Try to load from environment variables
        client_id = os.environ.get("YOUTUBE_CLIENT_ID")
        client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
        
        if client_id:
            self.CLIENT_ID = client_id
        if client_secret:
            self.CLIENT_SECRET = client_secret
        # Load redirect URI from environment or use default
        redirect_uri = os.environ.get("YOUTUBE_REDIRECT_URI")
        if redirect_uri:
            self.REDIRECT_URI = redirect_uri
        elif not self.REDIRECT_URI:
            from backend.config import YOUTUBE_REDIRECT_URI
            self.REDIRECT_URI = YOUTUBE_REDIRECT_URI
        # Load redirect URI from environment or use default
        redirect_uri = os.environ.get("YOUTUBE_REDIRECT_URI")
        if redirect_uri:
            self.REDIRECT_URI = redirect_uri
        elif not self.REDIRECT_URI:
            from backend.config import YOUTUBE_REDIRECT_URI
            self.REDIRECT_URI = YOUTUBE_REDIRECT_URI
        # Load redirect URI from environment or use default
        redirect_uri = os.environ.get("YOUTUBE_REDIRECT_URI")
        if redirect_uri:
            self.REDIRECT_URI = redirect_uri
        elif not self.REDIRECT_URI:
            from backend.config import YOUTUBE_REDIRECT_URI
            self.REDIRECT_URI = YOUTUBE_REDIRECT_URI
        
        # Also check if there's a config file
        config_file = BASE_DIR / "youtube_oauth.json"
        if config_file.exists():
            try:
                with open(config_file, "r") as f:
                    config = json.load(f)
                    if "client_id" in config:
                        self.CLIENT_ID = config["client_id"]
                    if "client_secret" in config:
                        self.CLIENT_SECRET = config["client_secret"]
                    if "redirect_uri" in config:
                        self.REDIRECT_URI = config["redirect_uri"]
                    if "redirect_uri" in config:
                        self.REDIRECT_URI = config["redirect_uri"]
                    if "redirect_uri" in config:
                        self.REDIRECT_URI = config["redirect_uri"]
            except Exception as e:
                logger.warning(f"Failed to load OAuth config: {e}")
    
    def _load_tokens(self) -> None:
        """Load saved authentication tokens."""
        if not self.TOKEN_FILE.exists():
            logger.debug("No saved tokens found")
            return
        
        try:
            with open(self.TOKEN_FILE, "r") as f:
                data = json.load(f)
            
            self._tokens = AuthToken.from_dict(data)
            
            # Check if token is still valid
            if self._tokens and not self._tokens.is_expired():
                self._is_authenticated = True
                logger.info("Loaded valid authentication tokens")
            else:
                self._is_authenticated = False
                logger.warning("Saved tokens are expired or invalid")
                
        except Exception as e:
            logger.error(f"Failed to load tokens: {e}")
            self._tokens = None
            self._is_authenticated = False
    
    def _save_tokens(self) -> None:
        """Save authentication tokens to file."""
        if not self._tokens:
            logger.debug("No tokens to save")
            return
        
        try:
            with open(self.TOKEN_FILE, "w") as f:
                json.dump(self._tokens.to_dict(), f, indent=2)
            logger.info(f"Saved tokens to: {self.TOKEN_FILE}")
        except Exception as e:
            logger.error(f"Failed to save tokens: {e}")
    
    def _clear_tokens(self) -> None:
        """Clear saved authentication tokens."""
        self._tokens = None
        self._is_authenticated = False
        self._user_info = None
        
        # Remove token file
        if self.TOKEN_FILE.exists():
            try:
                os.remove(self.TOKEN_FILE)
                logger.info(f"Removed token file: {self.TOKEN_FILE}")
            except Exception as e:
                logger.error(f"Failed to remove token file: {e}")
    
    def _generate_state(self) -> str:
        """Generate a secure random state string."""
        return secrets.token_urlsafe(32)
    
    def _generate_verifier(self) -> str:
        """Generate a secure random verifier string."""
        return secrets.token_urlsafe(64)
    
    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        return str(uuid.uuid4())
    
    @property
    def is_authenticated(self) -> bool:
        """Check if the user is authenticated."""
        return self._is_authenticated
    
    @property
    def tokens(self) -> Optional[AuthToken]:
        """Get the current authentication tokens."""
        return self._tokens
    
    @property
    def user_info(self) -> Optional[Dict[str, Any]]:
        """Get the authenticated user's information."""
        return self._user_info
    
    def get_cookies_path(self) -> Optional[Path]:
        """Get the path to the cookies file for ytmusicapi."""
        if YTMUSICAPI_COOKIES:
            cookies_path = Path(YTMUSICAPI_COOKIES)
            if cookies_path.exists():
                return cookies_path
        
        # Default location
        default_cookies = CACHE_DIR / "cookies.json"
        if default_cookies.exists():
            return default_cookies
        
        return None
    
    def create_oauth_state(self, redirect_uri: str = "http://localhost:8000/api/auth/callback") -> Tuple[str, str]:
        """
        Create a new OAuth state and verifier.
        
        Args:
            redirect_uri: The redirect URI for OAuth callback
            
        Returns:
            Tuple of (state, verifier)
        """
        verifier = self._generate_verifier()
        state = self._generate_state()
        
        # Generate the code challenge (PKCE)
        code_challenge = self._generate_code_challenge(verifier)
        
        # Store the state
        self._session_id = self._generate_session_id()
        _oauth_sessions[self._session_id] = OAuthState(
            state=state,
            verifier=verifier,
            redirect_uri=redirect_uri,
            created_at=datetime.utcnow(),
            used=False,
        ).to_dict()
        
        logger.info(f"Created OAuth state: {state[:8]}... (session: {self._session_id})")
        
        return state, code_challenge
    
    def _generate_code_challenge(self, verifier: str) -> str:
        """Generate PKCE code challenge from verifier."""
        import hashlib
        import base64
        
        # SHA256 hash of the verifier
        digest = hashlib.sha256(verifier.encode()).digest()
        
        # Base64 URL-safe encoding (no padding)
        challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
        
        return challenge
    
    def get_oauth_state(self, state: str) -> Optional[OAuthState]:
        """
        Get the OAuth state for a given state string.
        
        Args:
            state: The state string
            
        Returns:
            OAuthState object or None if not found
        """
        for session_id, session_data in _oauth_sessions.items():
            if session_data.get("state") == state:
                return OAuthState.from_dict(session_data)
        
        return None
    
    def mark_oauth_state_used(self, state: str) -> None:
        """Mark an OAuth state as used."""
        for session_id, session_data in _oauth_sessions.items():
            if session_data.get("state") == state:
                _oauth_sessions[session_id]["used"] = True
                logger.info(f"Marked OAuth state as used: {state[:8]}...")
                return
        
        logger.warning(f"OAuth state not found: {state[:8]}...")
    
    def get_auth_url(
        self,
        redirect_uri: str = "http://localhost:8000/api/auth/callback",
        scopes: Optional[list] = None,
        access_type: str = "offline",
        prompt: str = "consent",
    ) -> str:
        """
        Generate the OAuth 2.0 authorization URL.
        
        Args:
            redirect_uri: The redirect URI for OAuth callback
            scopes: List of OAuth scopes (defaults to YouTube Music scopes)
            access_type: "online" or "offline" (use "offline" for refresh tokens)
            prompt: "none", "consent", or "select_account"
            
        Returns:
            Authorization URL
        """
        if not self.CLIENT_ID:
            raise ValueError("YouTube CLIENT_ID not configured")
        
        # Use default scopes if not provided
        if scopes is None:
            scopes = self.OAUTH_SCOPES
        
        # Create state
        state, code_challenge = self.create_oauth_state(redirect_uri)
        
        # Build authorization URL
        base_url = "https://accounts.google.com/o/oauth2/v2/auth"
        
        # Build query parameters
        params = {
            "client_id": self.CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
            "access_type": access_type,
            "prompt": prompt,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        
        # Build URL with parameters
        url = base_url + "?" + "&".join([f"{k}={v}" for k, v in params.items()])
        
        logger.info(f"Generated OAuth URL for state: {state[:8]}...")
        
        return url
    
    def handle_oauth_callback(
        self,
        code: str,
        state: str,
        redirect_uri: str = "http://localhost:8000/api/auth/callback",
    ) -> bool:
        """
        Handle OAuth callback and exchange code for tokens.
        
        Args:
            code: Authorization code from callback
            state: State string from callback
            redirect_uri: Redirect URI used in the authorization request
            
        Returns:
            True if authentication succeeded, False otherwise
        """
        # Validate state
        oauth_state = self.get_oauth_state(state)
        if not oauth_state:
            logger.error(f"Invalid OAuth state: {state[:8]}...")
            return False
        
        # Mark state as used
        self.mark_oauth_state_used(state)
        
        # Get verifier
        verifier = oauth_state.verifier
        
        # Exchange code for tokens
        try:
            import requests
            
            # Token endpoint
            token_url = "https://oauth2.googleapis.com/token"
            
            # Prepare request data
            data = {
                "code": code,
                "client_id": self.CLIENT_ID,
                "client_secret": self.CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            }
            
            # Make request
            response = requests.post(token_url, data=data, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
                return False
            
            # Parse response
            token_data = response.json()
            
            # Create AuthToken
            self._tokens = AuthToken(
                access_token=token_data.get("access_token"),
                refresh_token=token_data.get("refresh_token"),
                token_type=token_data.get("token_type", "Bearer"),
                expires_at=datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 3600)),
                scopes=token_data.get("scope", "").split(" ") if token_data.get("scope") else None,
            )
            
            # Save tokens
            self._save_tokens()
            self._is_authenticated = True
            
            logger.info("OAuth callback handled successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to handle OAuth callback: {e}")
            return False
    
    def refresh_tokens(self) -> bool:
        """
        Refresh the access token using the refresh token.
        
        Returns:
            True if refresh succeeded, False otherwise
        """
        if not self._tokens or not self._tokens.refresh_token:
            logger.error("No refresh token available")
            return False
        
        if not self.CLIENT_ID or not self.CLIENT_SECRET:
            logger.error("Client ID or secret not configured")
            return False
        
        try:
            import requests
            
            # Token endpoint
            token_url = "https://oauth2.googleapis.com/token"
            
            # Prepare request data
            data = {
                "client_id": self.CLIENT_ID,
                "client_secret": self.CLIENT_SECRET,
                "grant_type": "refresh_token",
                "refresh_token": self._tokens.refresh_token,
            }
            
            # Make request
            response = requests.post(token_url, data=data, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
                return False
            
            # Parse response
            token_data = response.json()
            
            # Update tokens
            self._tokens.access_token = token_data.get("access_token")
            self._tokens.expires_at = datetime.utcnow() + timedelta(seconds=token_data.get("expires_in", 3600))
            
            # Save updated tokens
            self._save_tokens()
            self._is_authenticated = True
            
            logger.info("Tokens refreshed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to refresh tokens: {e}")
            self._is_authenticated = False
            return False
    
    def authenticate_with_cookies(self, cookies_file: Optional[Path] = None) -> bool:
        """
        Authenticate using cookies file for ytmusicapi.
        
        This is an alternative authentication method that doesn't require OAuth.
        
        Args:
            cookies_file: Path to cookies.json file. If None, uses the default.
            
        Returns:
            True if authentication succeeded, False otherwise
        """
        try:
            import ytmusicapi as ytma
            
            if cookies_file:
                cookies_path = cookies_file
            else:
                cookies_path = self.get_cookies_path()
            
            if not cookies_path or not cookies_path.exists():
                logger.error("Cookies file not found")
                return False
            
            # Test authentication by creating a YTMusic instance
            ytmusic = ytma.YTMusic(cookies_file=str(cookies_path))
            
            # Try to get user info to verify authentication
            user_info = ytmusic.get_user()
            
            if not user_info:
                logger.error("Failed to authenticate with cookies")
                return False
            
            # Save cookies path for later use
            self._user_info = user_info
            self._is_authenticated = True
            
            logger.info(f"Authenticated with cookies: {cookies_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to authenticate with cookies: {e}")
            return False
    
    def logout(self) -> None:
        """Log out and clear authentication."""
        self._clear_tokens()
        self._session_id = None
        self._user_info = None
        
        # Clear OAuth sessions
        global _oauth_sessions
        _oauth_sessions.clear()
        
        logger.info("Logged out successfully")
    
    def get_auth_status(self) -> Dict[str, Any]:
        """
        Get the current authentication status.
        
        Returns:
            Dictionary with authentication status
        """
        return {
            "is_authenticated": self._is_authenticated,
            "has_tokens": self._tokens is not None,
            "tokens_expired": self._tokens.is_expired() if self._tokens else True,
            "user_info": self._user_info,
            "client_configured": self.CLIENT_ID is not None,
        }
    
    def save_cookies(self, cookies: Dict[str, Any], path: Optional[Path] = None) -> bool:
        """
        Save cookies to a file.
        
        Args:
            cookies: Dictionary of cookies
            path: Path to save cookies. If None, uses the default.
            
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            if path is None:
                path = CACHE_DIR / "cookies.json"
            
            # Ensure directory exists
            os.makedirs(path.parent, exist_ok=True)
            
            # Save cookies
            with open(path, "w") as f:
                json.dump(cookies, f, indent=2)
            
            logger.info(f"Cookies saved to: {path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save cookies: {e}")
            return False
    
    def load_cookies(self, path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
        """
        Load cookies from a file.
        
        Args:
            path: Path to cookies file. If None, uses the default.
            
        Returns:
            Dictionary of cookies or None if not found
        """
        try:
            if path is None:
                path = self.get_cookies_path()
            
            if not path or not path.exists():
                return None
            
            with open(path, "r") as f:
                cookies = json.load(f)
            
            logger.info(f"Cookies loaded from: {path}")
            return cookies
            
        except Exception as e:
            logger.error(f"Failed to load cookies: {e}")
            return None
